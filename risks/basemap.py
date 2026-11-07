"""Fond de carte du back-office (carte des risques Leaflet + widgets carte de
l'admin GeoDjango), en un seul endroit pour pouvoir en changer facilement.

Le fond OpenStreetMap standard affiche les noms dans la langue locale
(chinois, arabe, dzongkha...). Les tuiles « OpenStreetMap France » affichent
les noms en français quand ils existent dans OpenStreetMap (champ name:fr),
et retombent sur le nom local sinon (petites localités, surtout).

Si un jour ce serveur ne suffit plus (limites d'usage, noms locaux illisibles
pour des petites localités), basculer sur un autre fond revient à changer
`FOND_ACTIF`. Ces serveurs de tuiles gratuits imposent un usage modéré : bien
pour un back-office utilisé par quelques personnes, pas pour l'API publique.
"""

FONDS = {
    # Noms en français lorsqu'ils existent.
    "osmfr": {
        "url": "https://{s}.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png",
        "attribution": "© Contributeurs OpenStreetMap — tuiles OpenStreetMap France",
        "max_zoom": 19,
    },
    # Noms en alphabet latin (anglais/transcrits), jamais en caractères locaux.
    "carto_voyager": {
        "url": "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
        "attribution": "© Contributeurs OpenStreetMap © CARTO",
        "max_zoom": 19,
    },
    # Fond d'origine (noms dans la langue locale).
    "osm": {
        "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© Contributeurs OpenStreetMap",
        "max_zoom": 19,
    },
}

FOND_ACTIF = "osmfr"


def _fond():
    return FONDS[FOND_ACTIF]


def contexte_leaflet():
    """Variables de template pour la carte Leaflet (risks/risk_map.html)."""
    fond = _fond()
    return {
        "tuiles_url": fond["url"],
        "tuiles_attribution": fond["attribution"],
        "tuiles_max_zoom": fond["max_zoom"],
    }


def contexte_openlayers():
    """Variables de template pour le widget carte OpenLayers (le motif
    d'URL d'OpenLayers est {a-c} là où Leaflet utilise {s})."""
    contexte = contexte_leaflet()
    contexte["tuiles_url"] = contexte["tuiles_url"].replace("{s}", "{a-c}")
    return contexte
