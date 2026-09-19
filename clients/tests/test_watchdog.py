"""Tests du watchdog "appli silencieuse" (Phase 4, cf. clients.watchdog)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from clients.models import NotificationLog, Utilisateur
from clients.watchdog import traiter_relances_silence, utilisateurs_en_silence


class UtilisateursEnSilenceTests(TestCase):
    def setUp(self):
        self.moment = timezone.now()

    def test_utilisateur_jamais_contacte_est_ignore(self):
        # last_contact_at nul : jamais démarré de check-in, pas de silence à
        # proprement parler (cf. Utilisateur.last_contact_at, nul avant le
        # premier contact).
        Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        self.assertEqual(utilisateurs_en_silence(self.moment), [])

    def test_utilisateur_recent_est_ignore(self):
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        u.last_contact_at = self.moment - timedelta(hours=1)
        u.save(update_fields=["last_contact_at"])

        self.assertEqual(utilisateurs_en_silence(self.moment), [])

    def test_utilisateur_silencieux_depuis_7h_est_detecte(self):
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        u.last_contact_at = self.moment - timedelta(hours=7, minutes=1)
        u.save(update_fields=["last_contact_at"])

        self.assertEqual(utilisateurs_en_silence(self.moment), [u])

    def test_utilisateur_silencieux_depuis_6h59_nest_pas_detecte(self):
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        u.last_contact_at = self.moment - timedelta(hours=6, minutes=59)
        u.save(update_fields=["last_contact_at"])

        self.assertEqual(utilisateurs_en_silence(self.moment), [])

    def test_pas_de_nouvelle_relance_avant_echeance_suivante(self):
        # Relance déjà envoyée il y a moins de 6h : pas encore l'heure de la
        # suivante (cf. §8 : 7h, 13h, 19h, 25h...).
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
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
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
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
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
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


class TraiterRelancesSilenceTests(TestCase):
    def test_envoie_et_journalise_pour_chaque_utilisateur_en_silence(self):
        moment = timezone.now()
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        u.last_contact_at = moment - timedelta(hours=8)
        u.save(update_fields=["last_contact_at"])

        notifies = traiter_relances_silence(moment)

        self.assertEqual(notifies, [u])
        self.assertTrue(
            NotificationLog.objects.filter(
                utilisateur=u,
                type_notification=NotificationLog.TypeNotification.RELANCE_SILENCE,
                canal=NotificationLog.Canal.SMS,
            ).exists()
        )

    def test_relance_ne_porte_ni_zone_ni_position(self):
        moment = timezone.now()
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        u.last_contact_at = moment - timedelta(hours=8)
        u.save(update_fields=["last_contact_at"])

        traiter_relances_silence(moment)

        log = NotificationLog.objects.get(
            utilisateur=u,
            type_notification=NotificationLog.TypeNotification.RELANCE_SILENCE,
            canal=NotificationLog.Canal.SMS,
        )
        self.assertIsNone(log.endemie)
        self.assertIsNone(log.position)

    def test_second_appel_immediat_ne_duplique_pas(self):
        moment = timezone.now()
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        u.last_contact_at = moment - timedelta(hours=8)
        u.save(update_fields=["last_contact_at"])

        traiter_relances_silence(moment)
        traiter_relances_silence(moment + timedelta(minutes=15))

        self.assertEqual(
            NotificationLog.objects.filter(
                utilisateur=u,
                type_notification=NotificationLog.TypeNotification.RELANCE_SILENCE,
                canal=NotificationLog.Canal.SMS,
            ).count(),
            1,
        )

    def test_relance_suivante_apres_nouvelle_echeance(self):
        moment = timezone.now()
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        u.last_contact_at = moment - timedelta(hours=8)
        u.save(update_fields=["last_contact_at"])

        traiter_relances_silence(moment)
        traiter_relances_silence(moment + timedelta(hours=6, minutes=1))

        self.assertEqual(
            NotificationLog.objects.filter(
                utilisateur=u,
                type_notification=NotificationLog.TypeNotification.RELANCE_SILENCE,
                canal=NotificationLog.Canal.SMS,
            ).count(),
            2,
        )

    def test_aucun_utilisateur_en_silence_ne_renvoie_liste_vide(self):
        self.assertEqual(traiter_relances_silence(timezone.now()), [])
