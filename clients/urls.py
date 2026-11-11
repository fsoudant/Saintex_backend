from django.urls import path

from .views import CacheView, InscriptionVerifierView, InscriptionView, MeContratView, MePreferencesView

urlpatterns = [
    path("inscription/", InscriptionView.as_view(), name="inscription"),
    path("inscription/verifier/", InscriptionVerifierView.as_view(), name="inscription_verifier"),
    path("cache/", CacheView.as_view(), name="cache"),
    path("me/", MePreferencesView.as_view(), name="me_preferences"),
    path("me/contrat/", MeContratView.as_view(), name="me_contrat"),
]
