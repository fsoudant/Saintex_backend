import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from .colors import average_rgb, parse_rgb, to_css
from .models import ConduiteATenir, Zone


def _risk_colors(endemies):
    return [parse_rgb(e.conduite_a_tenir.risque.couleur_legende) for e in endemies]


def build_risk_map_geojson(conduite_a_tenir=None):
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

    for zone in zones:
        endemies = list(zone.endemies.all())
        if conduite_a_tenir is not None:
            endemies = [e for e in endemies if e.conduite_a_tenir_id == conduite_a_tenir.pk]
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
                "geometry": json.loads(excluded.zone_exclue.geojson),
                "properties": {
                    "fill": to_css(patch_color),
                    "layer": "exclusion",
                    "nom": zone.nom,
                    "risque_exclu": excluded.conduite_a_tenir.risque.libelle_fr,
                },
            })

    return {"type": "FeatureCollection", "features": features}


def _conduite_a_tenir_from_request(request):
    pk = request.GET.get("conduite_a_tenir")
    if not pk:
        return None
    return get_object_or_404(ConduiteATenir, pk=pk)


@staff_member_required
def risk_map_geojson(request):
    conduite_a_tenir = _conduite_a_tenir_from_request(request)
    return JsonResponse(build_risk_map_geojson(conduite_a_tenir))


@staff_member_required
def risk_map_view(request):
    conduite_a_tenir = _conduite_a_tenir_from_request(request)
    return render(request, "risks/risk_map.html", {"conduite_a_tenir": conduite_a_tenir})
