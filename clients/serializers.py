from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .inscription import normaliser_email, normaliser_telephone
from .models import AlertReport, ParametreContrat, Utilisateur, valider_date_debut_contrat


class InscriptionSerializer(serializers.Serializer):
    """Inscription d'un voyageur depuis le tunnel du premier lancement (cf.
    saintex-spec-technique.md §6, §7 et clients.inscription). `consent` doit
    être vrai : le consentement RGPD explicite est préalable à tout traitement.
    `contract_duration` est le choix du voyageur dans le tunnel ; il sera
    confirmé par l'achat quand celui-ci existera.
    """

    email = serializers.EmailField(max_length=254)
    phone = serializers.CharField(max_length=32)
    email_active = serializers.BooleanField(required=False, default=True)
    push_active = serializers.BooleanField(required=False, default=True)
    reminder_delay = serializers.ChoiceField(
        choices=Utilisateur.DelaiRappel.choices,
        required=False,
        default=Utilisateur.DelaiRappel.QUOTIDIEN,
    )
    contract_start_date = serializers.DateField(required=False, allow_null=True)
    contract_duration = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=24)
    consent = serializers.BooleanField()

    def validate_email(self, value):
        return normaliser_email(value)

    def validate_phone(self, value):
        numero = normaliser_telephone(value)
        if numero is None:
            raise serializers.ValidationError(
                "Numéro de téléphone invalide : utilisez le format international (ex. +33612345678)."
            )
        return numero

    def validate_contract_start_date(self, value):
        if value is not None:
            try:
                valider_date_debut_contrat(None, value)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages[0] if exc.messages else str(exc))
        return value

    def validate_consent(self, value):
        if not value:
            raise serializers.ValidationError(
                "Le consentement au traitement de votre position est obligatoire."
            )
        return value


class VerificationCodeSerializer(serializers.Serializer):
    """Code de vérification reçu par email, avec la référence remise par l'inscription."""

    reference = serializers.UUIDField()
    code = serializers.RegexField(r"^\d{6}$", max_length=6, error_messages={"invalid": "Le code comporte 6 chiffres."})


class RapportAlerteSerializer(serializers.Serializer):
    """Un rapport d'alerte affichée par le téléphone (cf. spec §5, "Rapports
    d'alerte") : aucune coordonnée, seulement l'endémie (identifiant fourni par
    le cache), le type et les horodatages du téléphone.
    """

    id = serializers.UUIDField()
    endemie = serializers.IntegerField(min_value=1)
    type = serializers.ChoiceField(choices=AlertReport.Type.choices)
    affichee_le = serializers.DateTimeField()
    ouverte_le = serializers.DateTimeField(required=False, allow_null=True)
    cache_version = serializers.CharField(required=False, allow_blank=True, max_length=64)


class SanteAppliSerializer(serializers.Serializer):
    """État de santé de l'appli déclaré à chaque contact (cf. spec §4 et §8) :
    permet au serveur de détecter une protection dégradée."""

    localisation_toujours = serializers.BooleanField()
    notifications_autorisees = serializers.BooleanField()


# Plafond de rapports par contact : un téléphone resté longtemps hors ligne peut en
# accumuler, mais pas des milliers (au-delà il renverrait le reste au contact suivant).
MAX_RAPPORTS_PAR_CONTACT = 100


class CacheRequestSerializer(serializers.Serializer):
    """Contact du téléphone avec le serveur (cf. saintex-spec-technique.md §4 et
    §5). Aucune position : le cache est mondial. Peuvent être transmis, tous
    facultatifs :
    - `cache_version` : la version du cache déjà détenue — si elle est identique
      à la version courante, le serveur répond "inchangé" sans retransmettre
      les géométries ;
    - `sante` : l'état de santé de l'appli (permissions) ;
    - `rapports` : les rapports d'alerte en attente de remontée.
    Tout autre champ envoyé (par exemple une ancienne version de l'appli qui
    joindrait encore lat/lon) est ignoré, et jamais conservé.
    """

    cache_version = serializers.CharField(required=False, allow_blank=True, max_length=64)
    sante = SanteAppliSerializer(required=False)
    rapports = RapportAlerteSerializer(many=True, required=False, max_length=MAX_RAPPORTS_PAR_CONTACT)


class UtilisateurPreferencesSerializer(serializers.ModelSerializer):
    """Écran "préférences de notification" (cf. saintex-spec-technique.md §4) :
    lecture et mise à jour des seuls champs que l'utilisateur peut modifier
    lui-même. Le SMS n'apparaît pas ici — il n'est pas désactivable (cf. §8).
    """

    class Meta:
        model = Utilisateur
        fields = [
            "email", "phone", "email_active", "push_active", "reminder_delay",
            "subscription_status",
        ]
        read_only_fields = ["email", "phone", "subscription_status"]


class UtilisateurContratSerializer(serializers.ModelSerializer):
    """Écran de gestion du contrat (cf. saintex-spec-technique.md §6, décision
    réunion médicale) : consultation de la durée/dates et modification de
    `contract_start_date` tant que le contrat n'a pas démarré. `contract_duration`
    et `purchased_at` sont fixés par le processus d'achat (non encore implémenté,
    cf. spec §10) et restent en lecture seule ici.
    """

    contract_expiry_date = serializers.DateField(read_only=True)
    horizon_max_mois = serializers.SerializerMethodField()

    class Meta:
        model = Utilisateur
        fields = [
            "contract_duration",
            "purchased_at",
            "contract_start_date",
            "contract_expiry_date",
            "horizon_max_mois",
            "subscription_status",
        ]
        read_only_fields = ["contract_duration", "purchased_at", "subscription_status"]

    def get_horizon_max_mois(self, obj):
        # Exposé pour que le tunnel mobile connaisse la borne courante sans
        # la dupliquer en dur côté client (cf. ParametreContrat, éditable
        # sans déploiement tant que le chiffre exact n'est pas arrêté).
        return ParametreContrat.get_solo().horizon_max_mois

    def validate_contract_start_date(self, value):
        ancienne_valeur = self.instance.contract_start_date if self.instance else None
        if value != ancienne_valeur:
            try:
                valider_date_debut_contrat(ancienne_valeur, value)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages[0] if exc.messages else str(exc))
        return value
