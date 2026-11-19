"""Tests du watchdog "appli silencieuse" (Phase 4, cf. clients.watchdog)."""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from clients.models import NotificationLog, Utilisateur
from clients.watchdog import traiter_relances_silence, utilisateurs_en_silence

# Les tests partent des seuils de la spec (7 h, puis 6 h, sans limite) quel que soit le
# .env de la machine qui les lance ; les seuils configurables ont leurs propres tests.
SEUILS_DE_LA_SPEC = {
    "SAINTEX_SILENCE_PREMIERE_RELANCE_H": 7,
    "SAINTEX_SILENCE_RELANCES_SUIVANTES_H": 6,
    "SAINTEX_SILENCE_MAX_RELANCES": 0,
}


def _utilisateur(**extra):
    """Voyageur en plein contrat (départ il y a 10 jours, trois mois de contrat) :
    seuls les utilisateurs dont le contrat est actif sont relancés."""
    champs = {
        "email": "a@example.com",
        "phone": "+33600000000",
        "contract_start_date": timezone.localdate() - timedelta(days=10),
        "contract_duration": 3,
    }
    champs.update(extra)
    return Utilisateur.objects.create(**champs)


def _relances_sms(utilisateur):
    return NotificationLog.objects.filter(
        utilisateur=utilisateur,
        type_notification=NotificationLog.TypeNotification.RELANCE_SILENCE,
        canal=NotificationLog.Canal.SMS,
    )


@override_settings(**SEUILS_DE_LA_SPEC)
class UtilisateursEnSilenceTests(TestCase):
    def setUp(self):
        self.moment = timezone.now()

    def test_utilisateur_jamais_contacte_est_ignore(self):
        # last_contact_at nul : jamais démarré de check-in, pas de silence à
        # proprement parler (cf. Utilisateur.last_contact_at, nul avant le
        # premier contact).
        _utilisateur()
        self.assertEqual(utilisateurs_en_silence(self.moment), [])

    def test_utilisateur_recent_est_ignore(self):
        u = _utilisateur()
        u.last_contact_at = self.moment - timedelta(hours=1)
        u.save(update_fields=["last_contact_at"])

        self.assertEqual(utilisateurs_en_silence(self.moment), [])

    def test_utilisateur_silencieux_depuis_7h_est_detecte(self):
        u = _utilisateur()
        u.last_contact_at = self.moment - timedelta(hours=7, minutes=1)
        u.save(update_fields=["last_contact_at"])

        self.assertEqual(utilisateurs_en_silence(self.moment), [u])

    def test_utilisateur_silencieux_depuis_6h59_nest_pas_detecte(self):
        u = _utilisateur()
        u.last_contact_at = self.moment - timedelta(hours=6, minutes=59)
        u.save(update_fields=["last_contact_at"])

        self.assertEqual(utilisateurs_en_silence(self.moment), [])

    def test_pas_de_nouvelle_relance_avant_echeance_suivante(self):
        # Relance déjà envoyée il y a moins de 6h : pas encore l'heure de la
        # suivante (cf. §8 : 7h, 13h, 19h, 25h...).
        u = _utilisateur()
        u.last_contact_at = self.moment - timedelta(hours=10)
        u.save(update_fields=["last_contact_at"])
        NotificationLog.objects.create(
            utilisateur=u,
            type_notification=NotificationLog.TypeNotification.RELANCE_SILENCE,
            message="...",
            destinataire=u.phone,
            canal=NotificationLog.Canal.SMS,
        )
        # sent_at est auto_now_add : la relance ci-dessus est datée de
        # "maintenant", donc largement à moins de 6h de self.moment.
        self.assertEqual(utilisateurs_en_silence(self.moment), [])

    def test_nouvelle_relance_apres_echeance_suivante(self):
        u = _utilisateur()
        u.last_contact_at = self.moment - timedelta(hours=20)
        u.save(update_fields=["last_contact_at"])
        log = NotificationLog.objects.create(
            utilisateur=u,
            type_notification=NotificationLog.TypeNotification.RELANCE_SILENCE,
            message="...",
            destinataire=u.phone,
            canal=NotificationLog.Canal.SMS,
        )
        log.sent_at = self.moment - timedelta(hours=6, minutes=1)
        log.save(update_fields=["sent_at"])

        self.assertEqual(utilisateurs_en_silence(self.moment), [u])

    def test_relance_anterieure_au_dernier_contact_est_ignoree(self):
        # Cycle de silence précédent, clos par un check-in depuis : la
        # relance d'alors ne doit pas retarder le cycle actuel.
        u = _utilisateur()
        ancienne_relance = NotificationLog.objects.create(
            utilisateur=u,
            type_notification=NotificationLog.TypeNotification.RELANCE_SILENCE,
            message="...",
            destinataire=u.phone,
            canal=NotificationLog.Canal.SMS,
        )
        ancienne_relance.sent_at = self.moment - timedelta(days=2)
        ancienne_relance.save(update_fields=["sent_at"])

        # Nouveau cycle : contact reçu il y a 8h (postérieur à l'ancienne
        # relance) — sans check-in intermédiaire, l'ancienne relance aurait
        # sinon reporté l'échéance à tort.
        u.last_contact_at = self.moment - timedelta(hours=8)
        u.save(update_fields=["last_contact_at"])

        self.assertEqual(utilisateurs_en_silence(self.moment), [u])


@override_settings(**SEUILS_DE_LA_SPEC)
class RelancesPendantLeContratTests(TestCase):
    """Hors contrat, l'appli est volontairement muette (§6) : aucune relance."""

    def setUp(self):
        self.moment = timezone.now()

    def _en_silence(self, **extra):
        u = _utilisateur(**extra)
        u.last_contact_at = self.moment - timedelta(hours=30)
        u.save(update_fields=["last_contact_at"])
        return u

    def test_contrat_actif_est_relance(self):
        u = self._en_silence()
        self.assertEqual(utilisateurs_en_silence(self.moment), [u])

    def test_sans_date_de_depart_pas_de_relance(self):
        self._en_silence(contract_start_date=None)
        self.assertEqual(utilisateurs_en_silence(self.moment), [])

    def test_depart_dans_le_futur_pas_de_relance(self):
        self._en_silence(contract_start_date=timezone.localdate() + timedelta(days=20))
        self.assertEqual(utilisateurs_en_silence(self.moment), [])

    def test_contrat_expire_pas_de_relance(self):
        # Voyage terminé depuis longtemps, appli probablement désinstallée.
        self._en_silence(contract_start_date=timezone.localdate() - timedelta(days=400))
        self.assertEqual(utilisateurs_en_silence(self.moment), [])


@override_settings(**SEUILS_DE_LA_SPEC)
class TraiterRelancesSilenceTests(TestCase):
    def test_envoie_et_journalise_pour_chaque_utilisateur_en_silence(self):
        moment = timezone.now()
        u = _utilisateur()
        u.last_contact_at = moment - timedelta(hours=8)
        u.save(update_fields=["last_contact_at"])

        notifies = traiter_relances_silence(moment)

        self.assertEqual(notifies, [u])
        self.assertTrue(_relances_sms(u).exists())

    def test_relance_ne_porte_pas_de_zone(self):
        moment = timezone.now()
        u = _utilisateur()
        u.last_contact_at = moment - timedelta(hours=8)
        u.save(update_fields=["last_contact_at"])

        traiter_relances_silence(moment)

        self.assertIsNone(_relances_sms(u).get().endemie)

    def test_second_appel_immediat_ne_duplique_pas(self):
        moment = timezone.now()
        u = _utilisateur()
        u.last_contact_at = moment - timedelta(hours=8)
        u.save(update_fields=["last_contact_at"])

        traiter_relances_silence(moment)
        traiter_relances_silence(moment + timedelta(minutes=15))

        self.assertEqual(_relances_sms(u).count(), 1)

    def test_relance_suivante_apres_nouvelle_echeance(self):
        moment = timezone.now()
        u = _utilisateur()
        u.last_contact_at = moment - timedelta(hours=8)
        u.save(update_fields=["last_contact_at"])

        traiter_relances_silence(moment)
        traiter_relances_silence(moment + timedelta(hours=6, minutes=1))

        self.assertEqual(_relances_sms(u).count(), 2)

    def test_aucun_utilisateur_en_silence_ne_renvoie_liste_vide(self):
        self.assertEqual(traiter_relances_silence(timezone.now()), [])


class SeuilsConfigurablesTests(TestCase):
    """Seuils et plafond issus des réglages (SAINTEX_SILENCE_*), pour le pilote."""

    def setUp(self):
        self.moment = timezone.now()

    def _en_silence(self, heures):
        u = _utilisateur()
        u.last_contact_at = self.moment - timedelta(hours=heures)
        u.save(update_fields=["last_contact_at"])
        return u

    @override_settings(
        SAINTEX_SILENCE_PREMIERE_RELANCE_H=48,
        SAINTEX_SILENCE_RELANCES_SUIVANTES_H=24,
        SAINTEX_SILENCE_MAX_RELANCES=3,
    )
    def test_premier_seuil_configure(self):
        # 30 h de silence : au-delà de 7 h (spec) mais en dessous de 48 h (pilote).
        self._en_silence(30)
        self.assertEqual(utilisateurs_en_silence(self.moment), [])

    @override_settings(
        SAINTEX_SILENCE_PREMIERE_RELANCE_H=48,
        SAINTEX_SILENCE_RELANCES_SUIVANTES_H=24,
        SAINTEX_SILENCE_MAX_RELANCES=3,
    )
    def test_relance_apres_le_premier_seuil_configure(self):
        u = self._en_silence(49)
        self.assertEqual(utilisateurs_en_silence(self.moment), [u])

    @override_settings(
        SAINTEX_SILENCE_PREMIERE_RELANCE_H=7,
        SAINTEX_SILENCE_RELANCES_SUIVANTES_H=6,
        SAINTEX_SILENCE_MAX_RELANCES=2,
    )
    def test_plafond_de_relances_par_cycle_de_silence(self):
        u = self._en_silence(8)

        traiter_relances_silence(self.moment)
        traiter_relances_silence(self.moment + timedelta(hours=6, minutes=1))
        traiter_relances_silence(self.moment + timedelta(hours=12, minutes=5))
        traiter_relances_silence(self.moment + timedelta(hours=40))

        self.assertEqual(_relances_sms(u).count(), 2)

    @override_settings(
        SAINTEX_SILENCE_PREMIERE_RELANCE_H=7,
        SAINTEX_SILENCE_RELANCES_SUIVANTES_H=6,
        SAINTEX_SILENCE_MAX_RELANCES=2,
    )
    def test_le_plafond_repart_apres_un_nouveau_contact(self):
        # Un contact clôt le cycle de silence : le compteur de relances repart de zéro.
        u = self._en_silence(8)
        traiter_relances_silence(self.moment)
        traiter_relances_silence(self.moment + timedelta(hours=6, minutes=1))

        u.last_contact_at = self.moment + timedelta(hours=7)
        u.save(update_fields=["last_contact_at"])

        self.assertEqual(utilisateurs_en_silence(self.moment + timedelta(hours=15)), [u])

    @override_settings(
        SAINTEX_SILENCE_PREMIERE_RELANCE_H=7,
        SAINTEX_SILENCE_RELANCES_SUIVANTES_H=6,
        SAINTEX_SILENCE_MAX_RELANCES=0,
    )
    def test_zero_veut_dire_illimite(self):
        u = self._en_silence(8)

        for k in range(5):
            traiter_relances_silence(self.moment + timedelta(hours=7 * k))

        # Sans plafond, une relance part à chaque passage (les relances sont journalisées à
        # l'heure réelle, proche de self.moment : l'échéance suivante est toujours échue).
        self.assertEqual(_relances_sms(u).count(), 5)
        self.assertIn(u, utilisateurs_en_silence(self.moment + timedelta(hours=60)))
