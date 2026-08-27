from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin

from .models import ConduiteATenir, Endemie, Pays, Risque, Zone


@admin.register(Pays)
class PaysAdmin(GISModelAdmin):
    list_display = ("libelle_fr", "code", "source_id")
    search_fields = ("libelle_fr", "libelle_en", "code")
    gis_widget_kwargs = {"attrs": {"default_zoom": 3}}


@admin.register(Zone)
class ZoneAdmin(GISModelAdmin):
    list_display = ("nom", "source_id", "has_geometry", "pays", "note")
    list_filter = ("note", "pays")
    search_fields = ("nom", "source_id")
    autocomplete_fields = ("pays",)
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
class EndemieAdmin(GISModelAdmin):
    list_display = ("zone", "conduite_a_tenir", "date_debut", "date_fin", "has_exclusion")
    list_filter = ("conduite_a_tenir__risque",)
    search_fields = ("zone__nom", "conduite_a_tenir__code")
    autocomplete_fields = ("zone", "conduite_a_tenir")
    gis_widget_kwargs = {"attrs": {"default_zoom": 5}}

    @admin.display(boolean=True, description="Zone exclue")
    def has_exclusion(self, obj):
        return obj.zone_exclue is not None
