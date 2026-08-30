from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.text import Truncator

import shapely.affinity
import shapely.wkt

from .models import MOIS_CHOICES, ConduiteATenir, Endemie, Pays, Risque, Zone

_MOIS_LABELS = dict(MOIS_CHOICES)


def _shift_west_parts(shapely_geom):
    """Renvoie la liste des polygones d'une geometrie Shapely, en decalant de
    +360 tout polygone dont le bord gauche touche -180 (partie "ouest" issue
    d'un decoupage a l'antimeridien). Utilise pour recomposer une geometrie
    a cheval sur l'antimeridien en un seul bloc continu, que ce soit pour un
    apercu visuel ou pour calculer un centre correct.
    """
    parts = [shapely_geom] if shapely_geom.geom_type == "Polygon" else list(shapely_geom.geoms)
    return [
        shapely.affinity.translate(p, xoff=360) if p.bounds[0] <= -179.9 else p
        for p in parts
    ]


def zone_center_lonlat(geom):
    """Centre (lon, lat) d'une geometrie de Zone, correct meme a cheval sur
    l'antimeridien.

    Un centroide GEOS/Shapely classique fait une moyenne ponderee par aire
    des coordonnees *litterales*. Pour une zone decoupee en deux parties de
    part et d'autre de ±180° (Tuvalu, Kiribati, Fidji, Afrique_Asie_centrale
    — cf. build_zone_geom), ça place le centre au milieu du monde plutot que
    dans la zone elle-meme (ex. Fidji retombait a 64°E, dans l'ocean Indien,
    au lieu de ~179°E). On recompose donc la geometrie via
    _shift_west_parts avant de calculer le centroide, puis on ramene le
    resultat dans l'intervalle standard [-180, 180].
    """
    shapely_geom = shapely.wkt.loads(geom.wkt)
    shifted = _shift_west_parts(shapely_geom)
    combined = shapely.geometry.MultiPolygon(shifted) if len(shifted) > 1 else shifted[0]
    centroid = combined.centroid
    lon = centroid.x - 360 if centroid.x > 180 else centroid.x
    return lon, centroid.y


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
    parts = [shapely_geom] if shapely_geom.geom_type == "Polygon" else list(shapely_geom.geoms)
    if len(parts) < 2:
        return None

    touches_west = any(p.bounds[0] <= -179.9 for p in parts)
    touches_east = any(p.bounds[2] >= 179.9 for p in parts)
    if not (touches_west and touches_east):
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
    list_display = ("libelle_fr", "code", "source_id")
    search_fields = ("libelle_fr", "libelle_en", "code")
    gis_widget_kwargs = {"attrs": {"default_zoom": 3}}


@admin.register(Zone)
class ZoneAdmin(GISModelAdmin):
    list_display = ("nom", "source_id", "has_geometry", "pays_display", "note")
    list_filter = ("note", "pays")
    search_fields = ("nom", "source_id")
    autocomplete_fields = ("pays",)
    readonly_fields = ("apercu_antimeridien",)
    gis_widget_kwargs = {"attrs": {"default_zoom": 3}}

    @admin.display(boolean=True, description="Géométrie", ordering="geom")
    def has_geometry(self, obj):
        return obj.geom is not None

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
    list_display = ("code", "libelle_fr", "libelle_en", "ordre")
    search_fields = ("code", "libelle_fr", "libelle_en")
    ordering = ("ordre", "code")


@admin.register(ConduiteATenir)
class ConduiteATenirAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "risque",
        "legende_fr_courte",
        "facteurs_de_risque_fr_courte",
        "recommandation_fr_courte",
        "saison_display",
    )
    list_filter = ("risque",)
    search_fields = ("code", "legende_fr", "recommandation_fr", "facteurs_de_risque_fr")
    autocomplete_fields = ("risque",)

    @admin.display(description="Légende (fr)", ordering="legende_fr")
    def legende_fr_courte(self, obj):
        return format_html(
            '<span title="{}">{}</span>',
            obj.legende_fr,
            Truncator(obj.legende_fr).chars(50),
        )

    @admin.display(description="Facteurs de risque (fr)", ordering="facteurs_de_risque_fr")
    def facteurs_de_risque_fr_courte(self, obj):
        return format_html(
            '<span title="{}">{}</span>',
            obj.facteurs_de_risque_fr,
            Truncator(obj.facteurs_de_risque_fr).chars(80),
        )

    @admin.display(description="Recommandation (fr)", ordering="recommandation_fr")
    def recommandation_fr_courte(self, obj):
        return format_html(
            '<span title="{}">{}</span>',
            obj.recommandation_fr,
            Truncator(obj.recommandation_fr).chars(80),
        )

    @admin.display(description="Saison", ordering="saison_mois_debut")
    def saison_display(self, obj):
        if obj.saison_mois_debut is None:
            return "Toute l'année"
        return f"{_MOIS_LABELS[obj.saison_mois_debut]} → {_MOIS_LABELS[obj.saison_mois_fin]}"


@admin.register(Endemie)
class EndemieAdmin(GISModelAdmin):
    list_display = ("zone_display", "conduite_a_tenir", "date_debut", "date_fin", "has_exclusion")
    list_filter = ("conduite_a_tenir__risque",)
    search_fields = ("zone__nom", "conduite_a_tenir__code")
    autocomplete_fields = ("zone", "conduite_a_tenir")
    gis_widget_kwargs = {"attrs": {"default_zoom": 5}}

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
