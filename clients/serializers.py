from django.contrib.gis.geos import Point
from rest_framework import serializers

from .models import Utilisateur


class PositionInSerializer(serializers.Serializer):
    """Entrée du polling client (cf. Saintex.rtf §4) : juste lat/lon, la
    position est envoyée telle quelle, sans intelligence côté client.
    """

    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)

    def to_point(self):
        return Point(self.validated_data["lon"], self.validated_data["lat"], srid=4326)


class UtilisateurPreferencesSerializer(serializers.ModelSerializer):
    """Écran "préférences de notification" (cf. Saintex.rtf §4) : lecture et
    mise à jour des seuls champs que l'utilisateur peut modifier lui-même.
    Le SMS n'apparaît pas ici — il n'est pas désactivable (cf. §6).
    """

    class Meta:
        model = Utilisateur
        fields = ["email", "phone", "email_active", "push_active", "reminder_delay", "subscription_status"]
        read_only_fields = ["email", "phone", "subscription_status"]
