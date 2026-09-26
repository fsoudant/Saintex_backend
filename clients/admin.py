from django.contrib import admin

from risks.models import Risque

from .models import (
    NotificationLog,
    ParametreContrat,
    PreferenceChangeLog,
    PushToken,
    Utilisateur,
    UserRiskZoneStatus,
    VaccinationRisque,
)


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
        "voyage_en_famille", "contract_start_date", "last_contact_at", "consent_status",
    )
    list_filter = ("subscription_status", "email_active", "push_active", "voyage_en_famille", "consent_status")
    search_fields = ("email", "phone")
    readonly_fields = ("api_token", "created_at", "last_contact_at", "contract_expiry_date_display")
    inlines = [PushTokenInline, VaccinationRisqueInline]

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


@admin.register(UserRiskZoneStatus)
class UserRiskZoneStatusAdmin(admin.ModelAdmin):
    # Lecture seule : état calculé/maintenu par le moteur de détection de
    # zone à risque, pas un enregistrement à créer/modifier depuis l'admin.
    list_display = ("utilisateur", "endemie", "entered_at", "last_reminded_at")
    list_filter = ("endemie",)
    search_fields = ("utilisateur__email",)
    autocomplete_fields = ("utilisateur",)
    date_hierarchy = "entered_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    # Lecture seule : journal probatoire produit par le moteur d'envoi
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
