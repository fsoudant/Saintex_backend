from django.urls import path

from .views import MeContratView, MePreferencesView, PositionPollView

urlpatterns = [
    path("positions/", PositionPollView.as_view(), name="position_poll"),
    path("me/", MePreferencesView.as_view(), name="me_preferences"),
    path("me/contrat/", MeContratView.as_view(), name="me_contrat"),
]
