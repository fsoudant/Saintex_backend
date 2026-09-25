from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Utilisateur, valider_date_debut_contrat


class PositionInSerializer(serializers.Serializer):
    """Entrée du polling client (cf. saintex-spec-technique.md §4) : juste
    lat/lon, la position est envoyée telle quelle, sans intelligence côté client.
    """

    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)

    def to_point(self):
        return Point(self.validated_data["lon"], self.validated_data["lat"], srid=4326)


class UtilisateurPreferencesSerializer(serializers.ModelSerializer):
    """Écran "préférences de notification" (cf. saintex-spec-technique.md §4) :
    lecture et mise à jour des seuls champs que l'utilisateur peut modifier
    lui-même. Le SMS n'apparaît pas ici — il n'est pas désactivable (cf. §8).
    """

    class Meta:
        model = Utilisateur
        fields = ["email", "phone", "email_active", "push_active", "reminder_delay", "subscription_status"]
        read_only_fields = ["email", "phone", "subscription_status"]


class UtilisateurContratSerializer(serializers.ModelSerializer):
    """Écran de gestion du contrat (cf. saintex-spec-technique.md §6, décision
    réunion médicale) : consultation de la durée/dates et modification de
    `contract_start_date` tant que le contrat n'a pas démarré. `contract_duration`
    et `purchased_at` sont fixés par le processus d'achat (non encore implémenté,
    cf. spec §10) et restent en lecture seule ici.
    """

    contract_expiry_date = serializers.DateField(read_only=True)

    class Meta:
        model = Utilisateur
        fields = [
            "contract_duration",
            "purchased_at",
            "contract_start_date",
            "contract_expiry_date",
            "subscription_status",
        ]
        read_only_fields = ["contract_duration", "purchased_at", "subscription_status"]

    def validate_contract_start_date(self, value):
        ancienne_valeur = self.instance.contract_start_date if self.instance else None
        if value != ancienne_valeur:
            try:
                valider_date_debut_contrat(ancienne_valeur, value)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages[0] if exc.messages else str(exc))
        return value
