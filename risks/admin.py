import datetime
import json

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.contrib.admin.widgets import AdminDateWidget
from django.contrib.gis.admin import GISModelAdmin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.text import Truncator, slugify

import shapely.wkt

from . import geojson_io
from .geo_utils import _shift_west_parts, touches_antimeridian, zone_center_lonlat
from .models import MOIS_CHOICES, Endemie, Modulation, Pays, Risque, Zone
from .richtext import html_to_text
from .widgets import OSMFrWidget, RGBColorField, RichTextWidget

_MOIS_LABELS = dict(MOIS_CHOICES)


def _jour(valeur):
    """Date (jj/mm/aaaa) d'un instant, à l'heure locale ; "" si vide."""
    if valeur is None:
        return ""
    if timezone.is_aware(valeur):
        valeur = timezone.localtime(valeur)
    return valeur.strftime("%d/%m/%Y")


class _DateSeuleField(forms.DateField):
    """Champ de formulaire « date seule » pour un DateTimeField : l'heure n'a
    pas de sens métier pour une période de validité d'endémie. La date de
    début vaut 00:00:00 ce jour-là, la date de fin 23:59:59 (fin incluse)."""

    def __init__(self, *, fin_de_journee=False, **kwargs):
        self.fin_de_journee = fin_de_journee
        kwargs.setdefault("widget", AdminDateWidget)
        super().__init__(**kwargs)

    def prepare_value(self, value):
        if isinstance(value, datetime.datetime):
            if timezone.is_aware(value):
                value = timezone.localtime(value)
            return value.date()
        return value

    def to_python(self, value):
        jour = super().to_python(value)
        if jour is None:
            return None
        heure = datetime.time(23, 59, 59) if self.fin_de_journee else datetime.time.min
        return timezone.make_aware(datetime.datetime.combine(jour, heure))

    def has_changed(self, initial, data):
        # Compare des jours, pas des instants : l'heure n'est pas éditable.
        if self.disabled:
            return False
        avant = self.prepare_value(initial)
        try:
            apres = forms.DateField.to_python(self, data)
        except ValidationError:
            return True
        return avant != apres


class _RisqueAlphaFilter(admin.RelatedFieldListFilter):
    """Variante de RelatedFieldListFilter qui force le tri alphabetique
    (libelle_fr) des Risque dans le filtre lateral, au lieu de l'ordre
    manuel (Risque.ordre / RisqueAdmin.ordering) que Django utilise par
    defaut ici car Risque est enregistre avec ordering=('ordre', 'code').

    Cet ordre manuel reste volontairement intact pour la liste "Risque"
    elle-meme (RisqueAdmin.ordering) ; seul ce filtre est concerne.
    """

    def field_choices(self, field, request, model_admin):
        return field.get_choices(include_blank=False, ordering=("libelle_fr",))


def _antimeridian_preview_svg(geom, width=360, height=220, pad_ratio=0.12):
    """Aperçu SVG en lecture seule d'une Zone à cheval sur l'antiméridien.

    Le widget carte de l'admin (OpenLayers) cadre sa vue initiale en
    ajustant l'étendue brute de la géométrie (min/max des coordonnées).
    Pour un MultiPolygon dont une partie est collée à -180° et une autre à
    +180° (cf. build_zone_geom dans migrate_legacy_data — Tuvalu, Kiribati,
    Fidji, Afrique_Asie_centrale), cette étendue fait ~360° de large : la
    vue se dézoome sur le monde entier et la zone n'apparaît plus que sous
    forme de deux esquilles déconnectées aux bords opposés de l'écran.

    Cet aperçu recolle virtuellement les deux morceaux (via
    _shift_west_parts) pour les redessiner comme une forme continue, à
    bonne échelle. Rendu purement illustratif, séparé du widget d'édition :
    il ne modifie jamais la géométrie stockée ni ce qui est envoyé à la
    sauvegarde.

    Retourne None si la géométrie ne semble pas à cheval sur l'antiméridien
    (inutile d'afficher l'aperçu dans ce cas).
    """
    shapely_geom = shapely.wkt.loads(geom.wkt)
    if not touches_antimeridian(shapely_geom):
        return None  # MultiPolygon pour une autre raison (ex. buffer(0) sur auto-intersection)

    shifted = _shift_west_parts(shapely_geom)

    all_x = [x for p in shifted for x in p.exterior.coords.xy[0]]
    all_y = [y for p in shifted for y in p.exterior.coords.xy[1]]
    minx, maxx = min(all_x), max(all_x)
    miny, maxy = min(all_y), max(all_y)
    pad_x = (maxx - minx) * pad_ratio or 1
    pad_y = (maxy - miny) * pad_ratio or 1
    minx, maxx = minx - pad_x, maxx + pad_x
    miny, maxy = miny - pad_y, maxy + pad_y

    def to_px(lon, lat):
        x = (lon - minx) / (maxx - minx) * width
        y = (maxy - lat) / (maxy - miny) * height  # SVG : y croit vers le bas
        return x, y

    def ring_path(coords):
        pts = [to_px(x, y) for x, y in coords]
        return "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"

    paths = []
    for p in shifted:
        d = ring_path(p.exterior.coords)
        for interior in p.interiors:
            d += " " + ring_path(interior.coords)
        paths.append(
            f'<path d="{d}" fill="#7aa7d9" fill-opacity="0.65" '
            f'stroke="#2c5c8a" stroke-width="1" fill-rule="evenodd" />'
        )

    seam_x, _ = to_px(180, miny)
    seam_svg = (
        f'<line x1="{seam_x:.1f}" y1="0" x2="{seam_x:.1f}" y2="{height}" '
        f'stroke="#c0392b" stroke-width="1" stroke-dasharray="4,3" />'
        f'<text x="{seam_x + 4:.1f}" y="12" font-size="10" fill="#c0392b">180°</text>'
    )

    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg" style="background:#eef3f8;border:1px solid #ccc">'
        f"{''.join(paths)}{seam_svg}"
        f"</svg>"
    )


@admin.register(Pays)
class PaysAdmin(GISModelAdmin):
    gis_widget = OSMFrWidget
    list_display = ("libelle_fr", "code", "source_id")
    search_fields = ("libelle_fr", "libelle_en", "code")
    gis_widget_kwargs = {"attrs": {"default_zoom": 3}}


class ImportGeoJSONForm(forms.Form):
    """Formulaire de l'import GeoJSON d'une Zone : un fichier OU du texte
    collé, plus une simplification facultative."""

    fichier = forms.FileField(required=False, label="Fichier GeoJSON")
    texte = forms.CharField(
        required=False,
        label="ou JSON collé ici",
        widget=forms.Textarea(attrs={"rows": 12, "style": "width: 95%; font-family: monospace;"}),
    )
    tolerance = forms.FloatField(
        required=False,
        min_value=0,
        initial=0,
        label="Simplification (degrés)",
        help_text="0 = aucune. Saisir avec un point : 0.001 ≈ 100 m ; 0.01 ≈ 1 km. Allège les contours trop détaillés.",
    )

    def clean(self):
        donnees = super().clean()
        fichier = donnees.get("fichier")
        texte = (donnees.get("texte") or "").strip()
        if fichier:
            try:
                texte = fichier.read().decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ValidationError("Le fichier n'est pas encodé en UTF-8.")
        if not texte.strip():
            raise ValidationError("Choisis un fichier ou colle du JSON.")
        donnees["contenu"] = texte
        donnees["tolerance"] = donnees.get("tolerance") or 0.0
        return donnees


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    # ModelAdmin et non GISModelAdmin : la fiche de la zone n'embarque plus de
    # carte (cf. bouton "Voir la carte de la zone", template
    # admin/risks/zone/change_form.html, qui ouvre la carte du monde centrée sur
    # la zone et colorée par risque). La géométrie reste modifiable en texte
    # (EWKT) dans un bloc replié, pour les corrections ponctuelles (cf. Zone.note).
    list_display = ("nom", "source_id", "has_geometry", "pays_display", "note")
    list_filter = ("note", "pays")
    search_fields = ("nom", "source_id")
    autocomplete_fields = ("pays",)
    readonly_fields = ("apercu_antimeridien",)
    fieldsets = (
        (None, {"fields": ("source_id", "nom", "pays", "note")}),
        (
            "Géométrie (avancé — pour la visualiser, utiliser le bouton « Voir la carte de la zone »)",
            {"classes": ("collapse",), "fields": ("geom", "apercu_antimeridien")},
        ),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "geom":
            kwargs["widget"] = forms.Textarea(attrs={"rows": 8, "style": "width: 95%; font-family: monospace;"})
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(boolean=True, description="Géométrie", ordering="geom")
    def has_geometry(self, obj):
        return obj.geom is not None

    # --- Import / export GeoJSON (boutons de la fiche, cf. change_form.html) ---

    def get_urls(self):
        # Avant les URL par défaut : "<id>/<n'importe quoi>/" y est capté.
        propres = [
            path(
                "<path:object_id>/export-geojson/",
                self.admin_site.admin_view(self.export_geojson_view),
                name="risks_zone_export_geojson",
            ),
            path(
                "<path:object_id>/import-geojson/",
                self.admin_site.admin_view(self.import_geojson_view),
                name="risks_zone_import_geojson",
            ),
        ]
        return propres + super().get_urls()

    def export_geojson_view(self, request, object_id):
        zone = self.get_object(request, unquote(object_id))
        if zone is None:
            raise Http404
        if not self.has_view_permission(request, zone):
            raise PermissionDenied
        if zone.geom is None:
            messages.warning(request, "Cette zone n'a pas de géométrie à exporter.")
            return redirect(reverse("admin:risks_zone_change", args=[zone.pk]))
        contenu = json.dumps(geojson_io.zone_vers_geojson(zone), ensure_ascii=False, separators=(",", ":"))
        reponse = HttpResponse(contenu, content_type="application/geo+json; charset=utf-8")
        nom_fichier = f"zone-{zone.source_id}-{slugify(zone.nom) or 'zone'}.geojson"
        reponse["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
        return reponse

    def import_geojson_view(self, request, object_id):
        zone = self.get_object(request, unquote(object_id))
        if zone is None:
            raise Http404
        if not self.has_change_permission(request, zone):
            raise PermissionDenied

        if request.method == "POST":
            formulaire = ImportGeoJSONForm(request.POST, request.FILES)
            if formulaire.is_valid():
                try:
                    geometrie, resume = geojson_io.geojson_vers_multipolygon(
                        formulaire.cleaned_data["contenu"],
                        tolerance=formulaire.cleaned_data["tolerance"],
                    )
                except geojson_io.GeoJSONInvalide as erreur:
                    formulaire.add_error(None, str(erreur))
                else:
                    zone.geom = geometrie
                    zone.save(update_fields=["geom"])
                    detail = (
                        f"{resume['polygones']} polygone(s), {resume['points']} points, "
                        f"{geojson_io.DECIMALES} décimales"
                    )
                    self.log_change(request, zone, f"Géométrie remplacée par import GeoJSON ({detail}).")
                    messages.success(request, f"Géométrie importée : {detail}.")
                    for avertissement in resume["avertissements"]:
                        messages.warning(request, avertissement)
                    return redirect(reverse("admin:risks_zone_change", args=[zone.pk]))
        else:
            formulaire = ImportGeoJSONForm()

        contexte = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "original": zone,
            "form": formulaire,
            "title": f"Importer un GeoJSON — {zone.nom}",
            "a_une_geometrie": zone.geom is not None,
        }
        return TemplateResponse(request, "admin/risks/zone/import_geojson.html", contexte)

    @admin.display(description="Pays", ordering="pays__libelle_fr")
    def pays_display(self, obj):
        return obj.pays

    @admin.display(description="Aperçu (recollé à l'antiméridien)")
    def apercu_antimeridien(self, obj):
        if not obj or not obj.geom:
            return "—"
        svg = _antimeridian_preview_svg(obj.geom)
        if svg is None:
            return "— (zone non concernée par l'antiméridien)"
        return format_html(
            "{}<br><small>Vue illustrative uniquement : la partie côté -180° est "
            "décalée de +360° pour recomposer la zone en un seul bloc et compenser "
            "le cadrage automatique du widget carte ci-dessus (qui se dézoome sur le "
            "monde entier face à une géométrie coupée en deux). La géométrie "
            "réellement stockée n'est pas modifiée.</small>",
            mark_safe(svg),
        )


@admin.register(Risque)
class RisqueAdmin(admin.ModelAdmin):
    list_display = ("code", "libelle_fr", "libelle_en", "recommandation_fr_courte", "ordre")
    search_fields = ("code", "libelle_fr", "libelle_en")
    ordering = ("ordre", "code")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "couleur_legende":
            return RGBColorField(help_text=db_field.help_text)
        if db_field.name in ("recommandation_fr", "recommandation_en"):
            # Texte enrichi (gras, italique, taille, liens...) — cf. risks.richtext.
            kwargs["widget"] = RichTextWidget
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="Recommandation (fr)", ordering="recommandation_fr")
    def recommandation_fr_courte(self, obj):
        # Le champ contient du HTML (texte enrichi) : on affiche sa version
        # texte brut dans la liste, sans balises.
        texte = html_to_text(obj.recommandation_fr)
        return format_html(
            '<span title="{}">{}</span>',
            texte,
            Truncator(texte).chars(80),
        )


@admin.register(Modulation)
class ModulationAdmin(admin.ModelAdmin):
    list_display = ("code", "modulation_fr_courte", "saison_display")
    search_fields = ("code", "modulation_fr", "modulation_en")

    @admin.display(description="Modulation (fr)", ordering="modulation_fr")
    def modulation_fr_courte(self, obj):
        return format_html(
            '<span title="{}">{}</span>',
            obj.modulation_fr,
            Truncator(obj.modulation_fr).chars(100),
        )

    @admin.display(description="Période", ordering="saison_mois_debut")
    def saison_display(self, obj):
        if obj.saison_mois_debut is None:
            return "Toute l'année"
        return f"{_MOIS_LABELS[obj.saison_mois_debut]} → {_MOIS_LABELS[obj.saison_mois_fin]}"


@admin.register(Endemie)
class EndemieAdmin(GISModelAdmin):
    gis_widget = OSMFrWidget
    list_display = ("zone_display", "risque", "modulation", "debut_display", "fin_display", "has_exclusion")
    list_filter = (("risque", _RisqueAlphaFilter),)
    list_select_related = ("zone", "risque", "modulation")
    search_fields = ("zone__nom", "risque__libelle_fr", "modulation__code")
    autocomplete_fields = ("zone", "risque", "modulation")
    gis_widget_kwargs = {"attrs": {"default_zoom": 5}}

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # Période de validité : dates seules, sans heures.
        if db_field.name in ("date_debut", "date_fin"):
            return _DateSeuleField(
                fin_de_journee=db_field.name == "date_fin",
                required=False,
                label=db_field.verbose_name.capitalize(),
                help_text=db_field.help_text,
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="Date debut", ordering="date_debut")
    def debut_display(self, obj):
        return _jour(obj.date_debut)

    @admin.display(description="Date fin", ordering="date_fin")
    def fin_display(self, obj):
        return _jour(obj.date_fin)

    @admin.display(description="Zone", ordering="zone__nom")
    def zone_display(self, obj):
        return obj.zone

    @admin.display(boolean=True, description="Zone exclue", ordering="zone_exclue")
    def has_exclusion(self, obj):
        return obj.zone_exclue is not None

    def get_form(self, request, obj=None, **kwargs):
        """Centre la carte de `zone_exclue` sur la Zone déjà liée quand elle
        est encore vide, au lieu du centre par défaut du widget (~France).

        Ne s'applique qu'en modification (obj connu) : à la création, la
        Zone n'est pas encore choisie au moment où la carte est construite,
        donc le centre par défaut reste inchangé dans ce cas.
        """
        form = super().get_form(request, obj, **kwargs)
        if obj is not None and obj.zone_id and not obj.zone_exclue and obj.zone.geom:
            lon, lat = zone_center_lonlat(obj.zone.geom)
            widget = form.base_fields["zone_exclue"].widget
            widget.attrs["default_lon"] = lon
            widget.attrs["default_lat"] = lat
            widget.attrs["default_zoom"] = 6
        return form
