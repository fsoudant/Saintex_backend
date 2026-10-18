import shapely.geometry

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from .colors import average_rgb, parse_rgb, to_css
from .geo_utils import recompose_antimeridian
from .models import ConduiteATenir, Zone


def _risk_colors(endemies):
    return [parse_rgb(e.conduite_a_tenir.risque.couleur_legende) for e in endemies]


def _geom_to_geojson(geom):
    """GeoJSON d'une géométrie GEOS, recomposée si elle franchit
    l'antiméridien (cf. geo_utils.recompose_antimeridian) : sans ça, une
    zone comme Tuvalu/Kiribati/Fidji/Afrique_Asie_centrale s'affiche sur le
    Leaflet de la carte des risques comme deux esquilles tronquées aux deux
    bords opposés de la carte plate, au lieu d'un seul bloc continu autour
    de 180°/-180°.
    """
    return shapely.geometry.mapping(recompose_antimeridian(geom))


def build_risk_map_geojson(conduite_a_tenir=None, zone=None):
    """Construit une FeatureCollection GeoJSON :
    - une feature par Zone (géométrie complète), coloriée avec la moyenne
      des couleurs `Risque` de toutes les endémies qui s'y appliquent ;
    - une feature par exclusion (`Endemie.zone_exclue`), coloriée avec la
      moyenne des AUTRES risques de la même zone (sans le risque exclu) —
      transparente si aucun autre risque ne s'applique à cet endroit
      (vraie "zone saine").

    Si `conduite_a_tenir` est fourni, la carte se limite aux zones dont au
    moins une Endemie pointe vers cette conduite précise (vue depuis le
    bouton "Voir la carte des risques" de sa fiche détail) : chaque zone
    n'est alors colorée/étiquetée qu'avec cette conduite, sans mélange avec
    d'autres risques hors périmètre ; les exclusions deviennent de simples
    zones saines transparentes plutôt qu'une moyenne d'"autres risques"
    puisqu'aucun autre risque n'est affiché dans cette vue.

    Si `zone` est fourni (vue depuis le bouton "Voir la carte de la zone" de
    sa fiche détail), la carte se limite à cette seule zone, colorée avec la
    moyenne des couleurs de tous les risques de ses endémies ; la couleur
    propre à chaque risque est fournie dans `risques_couleurs` pour que la
    page puisse en afficher la légende. Une zone sans aucune endémie reste
    affichée (transparente) dans cette vue, contrairement à la carte globale
    qui ne montre que les zones à risque.

    Simplification actuelle, sans incidence sur les données réelles : ne
    gère pas le chevauchement de plusieurs exclusions sur une même zone
    (aucun cas de ce type aujourd'hui — à généraliser le jour où ça arrive).
    """
    features = []

    zones = (
        Zone.objects.filter(geom__isnull=False)
        .prefetch_related("endemies__conduite_a_tenir__risque")
    )
    if conduite_a_tenir is not None:
        zones = zones.filter(endemies__conduite_a_tenir=conduite_a_tenir).distinct()
    if zone is not None:
        zones = zones.filter(pk=zone.pk)

    for zone_obj in zones:
        endemies = list(zone_obj.endemies.all())
        if conduite_a_tenir is not None:
            endemies = [e for e in endemies if e.conduite_a_tenir_id == conduite_a_tenir.pk]
        if not endemies and zone is None:
            continue

        base_color = average_rgb(_risk_colors(endemies))
        risques_labels = sorted({e.conduite_a_tenir.risque.libelle_fr for e in endemies})
        couleurs_par_risque = {}
        for e in endemies:
            risque = e.conduite_a_tenir.risque
            couleurs_par_risque.setdefault(
                risque.libelle_fr, to_css(parse_rgb(risque.couleur_legende))
            )
        risques_couleurs = [
            {"risque": libelle, "couleur": couleur}
            for libelle, couleur in sorted(couleurs_par_risque.items())
        ]

        features.append({
            "type": "Feature",
            "geometry": _geom_to_geojson(zone_obj.geom),
            "properties": {
                "fill": to_css(base_color),
                "layer": "zone",
                "nom": zone_obj.nom,
                "risques": risques_labels,
                "risques_couleurs": risques_couleurs,
            },
        })

        for excluded in (e for e in endemies if e.zone_exclue):
            if conduite_a_tenir is not None:
                # Vue focalisée sur une seule conduite : la patch
                # d'exclusion est une simple zone saine transparente, sans
                # moyenne avec des risques hors périmètre affiché.
                patch_color = None
            else:
                autres_couleurs = _risk_colors(e for e in endemies if e.id != excluded.id)
                patch_color = average_rgb(autres_couleurs)
            features.append({
                "type": "Feature",
                "geometry": _geom_to_geojson(excluded.zone_exclue),
                "properties": {
                    "fill": to_css(patch_color),
                    "layer": "exclusion",
                    "nom": zone_obj.nom,
                    "risque_exclu": excluded.conduite_a_tenir.risque.libelle_fr,
                },
            })

    return {"type": "FeatureCollection", "features": features}


def _conduite_a_tenir_from_request(request):
    pk = request.GET.get("conduite_a_tenir")
    if not pk:
        return None
    return get_object_or_404(ConduiteATenir, pk=pk)


def _zone_from_request(request):
    pk = request.GET.get("zone")
    if not pk:
        return None
    return get_object_or_404(Zone, pk=pk)


@staff_member_required
def risk_map_geojson(request):
    conduite_a_tenir = _conduite_a_tenir_from_request(request)
    zone = _zone_from_request(request)
    return JsonResponse(build_risk_map_geojson(conduite_a_tenir, zone))


@staff_member_required
def risk_map_view(request):
    conduite_a_tenir = _conduite_a_tenir_from_request(request)
    zone = _zone_from_request(request)
    return render(
        request,
        "risks/risk_map.html",
        {"conduite_a_tenir": conduite_a_tenir, "zone": zone},
    )
