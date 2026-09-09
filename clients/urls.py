from django.urls import path

from .views import MePreferencesView, PositionPollView

urlpatterns = [
    path("positions/", PositionPollView.as_view(), name="position_poll"),
    path("me/", MePreferencesView.as_view(), name="me_preferences"),
]
