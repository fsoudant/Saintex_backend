from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
    # API des check-ins et endpoints back-office à ajouter ici (risks.urls)
]
