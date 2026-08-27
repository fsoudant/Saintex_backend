from django.contrib import admin
from django.urls import path

from risks.views import risk_map_geojson, risk_map_view

urlpatterns = [
    # Déclarées avant admin.site.urls : ce dernier capture tout le reste
    # de "admin/*", ces routes ne seraient jamais atteintes sinon.
    path("admin/risks/map/", risk_map_view, name="risk_map"),
    path("admin/risks/map/data/", risk_map_geojson, name="risk_map_geojson"),
    path("admin/", admin.site.urls),
    # API des check-ins et endpoints back-office à ajouter ici (risks.urls)
]
