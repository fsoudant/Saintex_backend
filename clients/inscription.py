"""Inscription d'un voyageur et récupération d'un compte existant (cf.
saintex-spec-technique.md §6 : le premier lancement crée le compte et remet le
jeton API au téléphone).

Deux cas, selon que l'email ou le téléphone saisis existent déjà :

- AUCUN compte ne correspond : le compte est créé (statut « essai », consentement
  RGPD horodaté) et le jeton est remis aussitôt.
- UN compte existe déjà (réinstallation, nouveau téléphone) : on ne remet PAS son
  jeton à la simple connaissance de l'email ou du numéro — n'importe qui pourrait
  sinon prendre le compte d'un autre. Un code à six chiffres est envoyé à l'email
  du compte ; saisi correctement, il remet un NOUVEAU jeton (l'ancien est révoqué :
  le téléphone perdu ou l'ancienne installation n'ont plus accès).

Limite connue : l'email et le téléphone d'un NOUVEAU compte ne sont pas vérifiés
à l'inscription. Quelqu'un pourrait donc s'inscrire avec les coordonnées d'un
autre avant lui ; l'intéressé passerait alors par la récupération ci-dessus (qui
révoque le jeton de l'imposteur). La vérification du téléphone par SMS suivra
avec le choix du prestataire SMS.
"""

import hashlib
import hmac
import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction

from .models import CodeVerification, Utilisateur, generate_api_token

logger = logging.getLogger(__name__)

DUREE_VALIDITE_CODE = timedelta(minutes=10)
DELAI_RENVOI_CODE = timedelta(seconds=60)
MAX_TENTATIVES = 5

_RE_TELEPHONE = re.compile(r"^\+[1-9]\d{7,14}$")


class EnvoiCodeEchoue(Exception):
    """L'email contenant le code de vérification n'a pas pu partir (SMTP
    indisponible, mauvais identifiants...)."""


def normaliser_email(email):
    return email.strip().lower()


def normaliser_telephone(telephone):
    """Retire espaces, points, tirets et parenthèses : « +33 6 12-34.56.78 » →
    « +33612345678 ». Renvoie None si le résultat n'est pas un numéro au format
    international (+, puis 8 à 15 chiffres)."""
    nettoye = re.sub(r"[\s.\-()]", "", telephone)
    return nettoye if _RE_TELEPHONE.match(nettoye) else None


def masquer_email(email):
    """« francois@gmail.com » → « f***@gmail.com » (indiqué au voyageur pour qu'il
    sache où chercher le code, sans divulguer l'adresse en entier)."""
    local, _, domaine = email.partition("@")
    return f"{local[:1]}***@{domaine}"


def trouver_compte_existant(email, telephone):
    """Compte correspondant à l'email (sans tenir compte de la casse), à défaut au
    téléphone ; None si aucun."""
    compte = Utilisateur.objects.filter(email__iexact=email).first()
    if compte is None:
        compte = Utilisateur.objects.filter(phone=telephone).first()
    return compte


def creer_utilisateur(donnees, maintenant):
    """Crée le compte voyageur. `donnees` : données validées par
    InscriptionSerializer. Lève IntegrityError si l'email ou le téléphone
    existent déjà (inscription simultanée)."""
    with transaction.atomic():
        return Utilisateur.objects.create(
            email=donnees["email"],
            phone=donnees["phone"],
            email_active=donnees["email_active"],
            push_active=donnees["push_active"],
            reminder_delay=donnees["reminder_delay"],
            contract_start_date=donnees.get("contract_start_date"),
            contract_duration=donnees.get("contract_duration"),
            consent_status=True,
            consent_date=maintenant,
        )


def inscrire_ou_recuperer(donnees, maintenant):
    """Point d'entrée de l'inscription. Renvoie `(utilisateur, code)` :
    - `(utilisateur, None)` : compte créé, le jeton peut être remis ;
    - `(utilisateur, code)` : compte existant, un code de vérification est parti (ou
      vient déjà de partir) par email ; `code.reference` identifie la demande.
    """
    existant = trouver_compte_existant(donnees["email"], donnees["phone"])
    if existant is None:
        try:
            return creer_utilisateur(donnees, maintenant), None
        except IntegrityError:
            existant = trouver_compte_existant(donnees["email"], donnees["phone"])
            if existant is None:
                raise
    return existant, demander_code(existant, maintenant)


def _empreinte(reference, code):
    """HMAC du code, lié à la référence : une base de données divulguée ne donne
    pas les codes (qui n'ont que 10^6 valeurs, d'où le HMAC avec la clé secrète
    plutôt qu'un simple hachage)."""
    message = f"{reference}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def demander_code(utilisateur, maintenant):
    """Envoie un code de vérification à l'email du compte et renvoie
    l'enregistrement. Si un code vient d'être envoyé (moins de
    DELAI_RENVOI_CODE), n'en envoie pas un nouveau — on renvoie celui en cours,
    pour qu'on ne puisse pas inonder une boîte mail — sauf s'il est épuisé."""
    recent = (
        utilisateur.codes_verification.filter(
            utilise_le__isnull=True,
            expire_le__gt=maintenant,
            cree_le__gt=maintenant - DELAI_RENVOI_CODE,
            tentatives__lt=MAX_TENTATIVES,
        )
        .order_by("-cree_le")
        .first()
    )
    if recent is not None:
        return recent

    code_clair = f"{secrets.randbelow(10**6):06d}"
    with transaction.atomic():
        # Un seul code valable à la fois : les précédents sont invalidés.
        utilisateur.codes_verification.filter(utilise_le__isnull=True).update(utilise_le=maintenant)
        enregistrement = CodeVerification(utilisateur=utilisateur, expire_le=maintenant + DUREE_VALIDITE_CODE)
        enregistrement.code_hash = _empreinte(enregistrement.reference, code_clair)
        enregistrement.save()

    minutes = int(DUREE_VALIDITE_CODE.total_seconds() // 60)
    try:
        send_mail(
            subject="Votre code de vérification Saintex",
            message=(
                f"Votre code de vérification Saintex : {code_clair}\n\n"
                f"Il est valable {minutes} minutes et ne sert qu'une fois.\n"
                "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : "
                "votre compte reste protégé."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[utilisateur.email],
            fail_silently=False,
        )
    except Exception as erreur:
        # Code jamais parti : on l'invalide, pour qu'un nouvel essai en envoie un
        # vrai plutôt que de renvoyer la référence d'un code que personne n'a reçu.
        enregistrement.utilise_le = maintenant
        enregistrement.save(update_fields=["utilise_le"])
        logger.exception("Envoi du code de vérification impossible (utilisateur %s)", utilisateur.pk)
        raise EnvoiCodeEchoue() from erreur
    logger.info("Code de vérification envoyé à l'utilisateur %s", utilisateur.pk)
    return enregistrement


def verifier_code(reference, code_saisi, maintenant):
    """Vérifie un code et, s'il est bon, renvoie le compte avec un NOUVEAU jeton
    d'API (l'ancien est révoqué). Renvoie None dans tous les cas d'échec (référence
    inconnue, code périmé, déjà utilisé, trop d'essais, code erroné), sans les
    distinguer : l'appelant ne doit rien en apprendre d'utile pour deviner un code."""
    with transaction.atomic():
        enregistrement = (
            CodeVerification.objects.select_for_update()
            .select_related("utilisateur")
            .filter(reference=reference)
            .first()
        )
        if (
            enregistrement is None
            or enregistrement.utilise_le is not None
            or enregistrement.expire_le <= maintenant
            or enregistrement.tentatives >= MAX_TENTATIVES
        ):
            return None

        enregistrement.tentatives += 1
        attendu = enregistrement.code_hash
        if not hmac.compare_digest(attendu, _empreinte(enregistrement.reference, code_saisi)):
            enregistrement.save(update_fields=["tentatives"])
            return None

        enregistrement.utilise_le = maintenant
        enregistrement.save(update_fields=["tentatives", "utilise_le"])

        utilisateur = enregistrement.utilisateur
        utilisateur.api_token = generate_api_token()
        utilisateur.save(update_fields=["api_token"])
        return utilisateur
