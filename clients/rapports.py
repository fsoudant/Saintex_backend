"""
Enregistrement des rapports d'alerte remontés par le téléphone (cf.
saintex-spec-technique.md §5 "Rapports d'alerte" et §8) : la détection se fait
sur le téléphone, qui affiche l'alerte puis la rapporte au serveur au contact
suivant. Le serveur :

- enregistre chaque rapport (AlertReport), sans doublon : le téléphone peut
  renvoyer le même rapport (coupure réseau, mise à jour de l'ouverture) ;
- envoie le SMS court de sauvegarde pour chaque NOUVELLE alerte d'entrée
  (option B du §8) ; les rappels restent locaux ;
- acquitte les rapports reçus, pour que le téléphone purge sa file d'attente.
"""

import logging

from django.utils import timezone

from risks.models import Endemie

from .models import AlertReport
from .notifications import envoyer_sms_alerte

logger = logging.getLogger("saintex.rapports")


def enregistrer_rapports(utilisateur, rapports, moment=None):
    """Enregistre les `rapports` (liste de dicts validés par
    RapportAlerteSerializer) pour `utilisateur`. Retourne la liste des
    identifiants (str) acquittés : ceux enregistrés, ou déjà connus. Un
    rapport dont le traitement échoue n'est PAS acquitté : le téléphone le
    renverra au contact suivant plutôt que de le perdre.
    """
    moment = moment or timezone.now()
    acquittes = []

    for donnees in rapports:
        try:
            endemie = (
                Endemie.objects.select_related("zone", "conduite_a_tenir__risque")
                .filter(pk=donnees["endemie"])
                .first()
            )
            rapport, cree = AlertReport.objects.get_or_create(
                utilisateur=utilisateur,
                identifiant_client=donnees["id"],
                defaults={
                    "endemie": endemie,
                    # Zone et risque recopiés en texte : l'endémie peut disparaître
                    # ou évoluer ensuite, ce qui compte c'est ce qui a été rapporté.
                    "zone_nom": endemie.zone.nom if endemie else "",
                    "risque_code": endemie.conduite_a_tenir.risque.code if endemie else "",
                    "type_alerte": donnees["type"],
                    "affichee_le": donnees["affichee_le"],
                    "ouverte_le": donnees.get("ouverte_le"),
                    "cache_version": donnees.get("cache_version", ""),
                },
            )
            if cree:
                if rapport.type_alerte == AlertReport.Type.ENTREE:
                    envoyer_sms_alerte(utilisateur, rapport, moment)
            elif donnees.get("ouverte_le") and rapport.ouverte_le is None:
                # Même rapport renvoyé : seule l'ouverture peut avoir changé.
                rapport.ouverte_le = donnees["ouverte_le"]
                rapport.save(update_fields=["ouverte_le"])
            acquittes.append(str(donnees["id"]))
        except Exception:
            logger.exception("Échec d'enregistrement du rapport d'alerte %s", donnees.get("id"))

    return acquittes
