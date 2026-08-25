from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import ConduiteATenir, Endemie, Pays, Risque, Zone, ZoneSaine


@admin.register(Pays)
class PaysAdmin(GISModelAdmin):
    list_display = ("libelle_fr", "code", "source_id")
    search_fields = ("libelle_fr", "libelle_en", "code")
    gis_widget_kwargs = {"attrs": {"default_zoom": 3}}


@admin.register(Zone)
class ZoneAdmin(GISModelAdmin):
    list_display = ("nom", "source_id", "has_geometry", "note")
    list_filter = ("note",)
    search_fields = ("nom", "source_id")
    gis_widget_kwargs = {"attrs": {"default_zoom": 3}}

    @admin.display(boolean=True, description="Géométrie")
    def has_geometry(self, obj):
        return obj.geom is not None


@admin.register(Risque)
class RisqueAdmin(admin.ModelAdmin):
    list_display = ("code", "libelle_fr", "libelle_en", "ordre")
    search_fields = ("code", "libelle_fr", "libelle_en")
    ordering = ("ordre", "code")


@admin.register(ConduiteATenir)
class ConduiteATenirAdmin(admin.ModelAdmin):
    list_display = ("code", "risque", "legende_fr")
    list_filter = ("risque",)
    search_fields = ("code", "legende_fr", "recommandation_fr")
    autocomplete_fields = ("risque",)


@admin.register(Endemie)
class EndemieAdmin(admin.ModelAdmin):
    list_display = ("zone", "conduite_a_tenir", "date_debut", "date_fin")
    list_filter = ("conduite_a_tenir__risque",)
    search_fields = ("zone__nom", "conduite_a_tenir__code")
    autocomplete_fields = ("zone", "conduite_a_tenir")


@admin.register(ZoneSaine)
class ZoneSaineAdmin(GISModelAdmin):
    list_display = ("libelle_fr", "zone", "conduite_a_tenir", "pays")
    list_filter = ("conduite_a_tenir__risque", "pays")
    search_fields = ("libelle_fr", "libelle_en")
    autocomplete_fields = ("zone", "conduite_a_tenir", "pays")
    gis_widget_kwargs = {"attrs": {"default_zoom": 5}}
