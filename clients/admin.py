from django.contrib import admin

from .models import (
    AlertReport,
    NotificationLog,
    ParametreContrat,
    PreferenceChangeLog,
    PushToken,
    Utilisateur,
)


class PushTokenInline(admin.TabularInline):
    model = PushToken
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(Utilisateur)
class UtilisateurAdmin(admin.ModelAdmin):
    list_display = (
        "email", "phone", "subscription_status", "email_active", "push_active",
        "contract_start_date", "last_contact_at", "consent_status",
    )
    list_filter = ("subscription_status", "email_active", "push_active", "consent_status")
    search_fields = ("email", "phone")
    readonly_fields = (
        "api_token", "created_at", "last_contact_at", "contract_expiry_date_display",
        "localisation_toujours", "notifications_autorisees", "sante_declaree_le",
    )
    inlines = [PushTokenInline]

    def contract_expiry_date_display(self, obj):
        # contract_expiry_date est une propriété calculée (début + durée),
        # pas un champ de modèle — exposée en lecture seule via cette méthode.
        return obj.contract_expiry_date

    contract_expiry_date_display.short_description = "Date d'expiration du contrat"


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


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    # Lecture seule : journal probatoire des messages envoyés par le serveur
    # (cf. §9), jamais saisi/modifié à la main.
    list_display = (
        "utilisateur", "type_notification", "canal", "statut", "destinataire", "sent_at",
    )
    list_filter = ("type_notification", "canal", "statut")
    search_fields = ("utilisateur__email", "destinataire")
    autocomplete_fields = ("utilisateur",)
    date_hierarchy = "sent_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AlertReport)
class AlertReportAdmin(admin.ModelAdmin):
    # Lecture seule : rapports remontés par les téléphones (cf. spec §5, §9),
    # jamais saisis/modifiés à la main — journal probatoire.
    list_display = (
        "utilisateur", "type_alerte", "zone_nom", "risque_code",
        "affichee_le", "ouverte_le", "recue_le",
    )
    list_filter = ("type_alerte", "risque_code")
    search_fields = ("utilisateur__email", "zone_nom")
    autocomplete_fields = ("utilisateur",)
    date_hierarchy = "recue_le"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ParametreContrat)
class ParametreContratAdmin(admin.ModelAdmin):
    # Singleton (cf. ParametreContrat.get_solo) : un seul ajout possible,
    # jamais de suppression — sinon valider_date_debut_contrat n'aurait
    # plus de ligne à lire (elle en recrée une via get_or_create, mais
    # autant éviter le clignotement à paramètres remis à la valeur par
    # défaut entre-temps).
    list_display = ("horizon_max_mois",)

    def has_add_permission(self, request):
        return not ParametreContrat.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
