"""
Détection de zone(s) à risque active(s) pour une position donnée
(cf. saintex-spec-technique.md §7/§8) — cœur du moteur de notification.

Utilise ST_Covers (lookup GeoDjango `covers`), une fonction PostGIS
nativement définie sur le type geography (contrairement à ST_Contains, qui
n'existe que sur geometry et forcerait un cast implicite — cassant le calcul
pour les zones à cheval sur l'antiméridien : Tuvalu, Kiribati, Fidji,
Afrique_Asie_centrale, cf. risks.geo_utils, qui traite le même problème mais
pour le rendu Leaflet, pas pour cette requête-ci). `covers` inclut la
frontière du polygone (contrairement à `contains`), ce qui est le
comportement souhaité : un voyageur exactement sur la limite d'une zone doit
être alerté.
"""

from django.db.models import Q
from django.utils import timezone

from .models import Endemie


def zones_actives_pour_point(point, moment=None):
    """Renvoie la liste des Endemie actives à `moment` (défaut : maintenant)
    dont la Zone couvre `point`.

    Exclut :
    - les Endemie dont `zone_exclue` couvre aussi `point` (cf.
      Endemie.zone_exclue — ex. une ville épargnée dans une zone à risque) ;
    - les Endemie hors de leur période de validité (`date_debut`/`date_fin`) ;
    - les Endemie dont la ConduiteATenir liée est hors saison
      (cf. ConduiteATenir.is_in_season).

    Renvoie une liste (pas un queryset) car le filtre de saisonnalité est
    fait en Python — is_in_season() n'est pas traduisible en requête SQL
    simple vu la gestion des périodes à cheval sur le nouvel an.
    """
    moment = moment or timezone.now()

    candidats = (
        Endemie.objects.filter(zone__geom__covers=point)
        .filter(Q(date_debut__isnull=True) | Q(date_debut__lte=moment))
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=moment))
        .exclude(zone_exclue__covers=point)
        .select_related("conduite_a_tenir", "conduite_a_tenir__risque", "zone")
    )

    return [e for e in candidats if e.conduite_a_tenir.is_in_season(moment)]
