import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render

from .colors import average_rgb, parse_rgb, to_css
from .models import Zone


def _risk_colors(endemies):
    return [parse_rgb(e.conduite_a_tenir.risque.couleur_legende) for e in endemies]


def build_risk_map_geojson():
    """Construit une FeatureCollection GeoJSON :
    - une feature par Zone (géométrie complète), coloriée avec la moyenne
      des couleurs `Risque` de toutes les endémies qui s'y appliquent ;
    - une feature par exclusion (`Endemie.zone_exclue`), coloriée avec la
      moyenne des AUTRES risques de la même zone (sans le risque exclu) —
      transparente si aucun autre risque ne s'applique à cet endroit
      (vraie "zone saine").

    Simplification actuelle, sans incidence sur les données réelles : ne
    gère pas le chevauchement de plusieurs exclusions sur une même zone
    (aucun cas de ce type aujourd'hui — à généraliser le jour où ça arrive).
    """
    features = []

    zones = (
        Zone.objects.filter(geom__isnull=False)
        .prefetch_related("endemies__conduite_a_tenir__risque")
    )

    for zone in zones:
        endemies = list(zone.endemies.all())
        if not endemies:
            continue

        base_color = average_rgb(_risk_colors(endemies))
        risques_labels = sorted({e.conduite_a_tenir.risque.libelle_fr for e in endemies})

        features.append({
            "type": "Feature",
            "geometry": json.loads(zone.geom.geojson),
            "properties": {
                "fill": to_css(base_color),
                "layer": "zone",
                "nom": zone.nom,
                "risques": risques_labels,
            },
        })

        for excluded in (e for e in endemies if e.zone_exclue):
            autres_couleurs = _risk_colors(e for e in endemies if e.id != excluded.id)
            patch_color = average_rgb(autres_couleurs)
            features.append({
                "type": "Feature",
                "geometry": json.loads(excluded.zone_exclue.geojson),
                "properties": {
                    "fill": to_css(patch_color),
                    "layer": "exclusion",
                    "nom": zone.nom,
                    "risque_exclu": excluded.conduite_a_tenir.risque.libelle_fr,
                },
            })

    return {"type": "FeatureCollection", "features": features}


@staff_member_required
def risk_map_geojson(request):
    return JsonResponse(build_risk_map_geojson())


@staff_member_required
def risk_map_view(request):
    return render(request, "risks/risk_map.html")
