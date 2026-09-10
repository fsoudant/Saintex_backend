from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from risks.models import Risque

from .models import PreferenceChangeLog, Position, PushToken, Utilisateur, VaccinationRisque


class PushTokenInline(admin.TabularInline):
    model = PushToken
    extra = 0
    readonly_fields = ("created_at",)


class VaccinationRisqueInline(admin.TabularInline):
    model = VaccinationRisque
    extra = 0
    readonly_fields = ("declared_at",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Ne propose que les risques ayant un vaccin (cf. Risque.vaccin_disponible) —
        # cohérent avec la contrainte imposée par VaccinationRisque.clean().
        if db_field.name == "risque":
            kwargs["queryset"] = Risque.objects.filter(vaccin_disponible=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Utilisateur)
class UtilisateurAdmin(admin.ModelAdmin):
    list_display = (
        "email", "phone", "subscription_status", "email_active", "push_active",
        "last_seen_at", "consent_status",
    )
    list_filter = ("subscription_status", "email_active", "push_active", "consent_status")
    search_fields = ("email", "phone")
    readonly_fields = ("api_token", "created_at", "last_seen_at")
    inlines = [PushTokenInline, VaccinationRisqueInline]


@admin.register(Position)
class PositionAdmin(GISModelAdmin):
    # Lecture seule : ce sont des données reçues automatiquement du client,
    # pas des enregistrements à créer/modifier depuis l'admin.
    list_display = ("utilisateur", "received_at")
    list_filter = ("utilisateur",)
    date_hierarchy = "received_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PreferenceChangeLog)
class PreferenceChangeLogAdmin(admin.ModelAdmin):
    list_display = ("utilisateur", "champ", "ancienne_valeur", "nouvelle_valeur", "changed_at")
    list_filter = ("champ",)
    search_fields = ("utilisateur__email",)
    date_hierarchy = "changed_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(VaccinationRisque)
class VaccinationRisqueAdmin(admin.ModelAdmin):
    # Vue transversale pour l'équipe médicale (ex. "qui est couvert pour la
    # fièvre jaune ?"), en complément de l'inline sur UtilisateurAdmin qui
    # ne montre qu'un voyageur à la fois.
    list_display = ("utilisateur", "risque", "vaccine", "declared_at")
    list_filter = ("risque", "vaccine")
    search_fields = ("utilisateur__email",)
    autocomplete_fields = ("utilisateur", "risque")
    readonly_fields = ("declared_at",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "risque":
            kwargs["queryset"] = Risque.objects.filter(vaccin_disponible=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
