from django.urls import path

from .views import CacheView, MeContratView, MePreferencesView

urlpatterns = [
    path("cache/", CacheView.as_view(), name="cache"),
    path("me/", MePreferencesView.as_view(), name="me_preferences"),
    path("me/contrat/", MeContratView.as_view(), name="me_contrat"),
]
