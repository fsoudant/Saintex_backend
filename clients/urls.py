from django.urls import path

from .views import CacheView, MeContratView, MePreferencesView, PositionPollView

urlpatterns = [
    path("cache/", CacheView.as_view(), name="cache"),
    path("positions/", PositionPollView.as_view(), name="position_poll"),
    path("me/", MePreferencesView.as_view(), name="me_preferences"),
    path("me/contrat/", MeContratView.as_view(), name="me_contrat"),
]
