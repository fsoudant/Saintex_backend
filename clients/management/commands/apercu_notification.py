"""
Aperçu des messages de notification d'une conduite à tenir, sans rien envoyer
ni écrire en base — pour que l'équipe médicale voie comment la mise en forme
de sa recommandation (gras, listes, liens...) est transformée selon le canal
(cf. saintex-spec-technique.md §8, texte enrichi) :

- texte brut : SMS, push et notification locale hors ligne (liens réduits à
  « texte (url) », listes conservées) + taille estimée en segments SMS ;
- HTML : email.

Usage :
    python manage.py apercu_notification                 # liste les conduites
    python manage.py apercu_notification PAL_T1          # alerte d'entrée en zone
    python manage.py apercu_notification PAL_T1 --rappel # message de rappel
    python manage.py apercu_notification PAL_T1 --html-fichier /tmp/apercu.html
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from clients.models import NotificationLog
from clients.notifications import _composer_message
from risks.models import ConduiteATenir, Endemie

# Alphabet SMS standard (GSM 03.38) : 160 caractères par SMS seul, 153 par
# segment quand le message est découpé. Un caractère hors alphabet (ex. « ê »,
# « œ », apostrophe typographique, emoji) bascule tout le message en UCS-2 :
# 70 caractères par SMS seul, 67 par segment — le coût peut donc doubler.
_GSM_BASE = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM_EXTENSION = "^{}\\[~]|€"  # comptent pour 2 caractères


def estimer_segments_sms(texte):
    """Retourne (encodage, longueur, nombre de segments) pour un SMS."""
    if all(c in _GSM_BASE or c in _GSM_EXTENSION for c in texte):
        longueur = sum(2 if c in _GSM_EXTENSION else 1 for c in texte)
        seul, par_segment, encodage = 160, 153, "GSM-7"
    else:
        longueur = len(texte)
        seul, par_segment, encodage = 70, 67, "UCS-2"
    if longueur <= seul:
        return encodage, longueur, 1
    return encodage, longueur, -(-longueur // par_segment)


class Command(BaseCommand):
    help = (
        "Affiche, sans l'envoyer, le message de notification d'une conduite à "
        "tenir : version texte brut (SMS/push) et version HTML (email)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "code", nargs="?",
            help="Code de la conduite à tenir (ex. PAL_T1). Sans code : liste des conduites.",
        )
        parser.add_argument(
            "--rappel", action="store_true",
            help="Aperçu du message de rappel plutôt que de l'alerte d'entrée en zone.",
        )
        parser.add_argument(
            "--html-fichier", metavar="CHEMIN",
            help="Écrit aussi la version email dans une page HTML à ouvrir dans un navigateur.",
        )

    def handle(self, *args, **options):
        code = options["code"]
        if not code:
            self._lister_conduites()
            return

        try:
            conduite = ConduiteATenir.objects.select_related("risque").get(code=code)
        except ConduiteATenir.DoesNotExist:
            raise CommandError(
                f"Conduite à tenir « {code} » introuvable "
                "(lancer la commande sans argument pour lister les codes)."
            )

        type_notification = (
            NotificationLog.TypeNotification.RAPPEL_ZONE
            if options["rappel"]
            else NotificationLog.TypeNotification.ALERTE_ZONE
        )
        # Endemie non enregistrée : le message ne dépend que de la conduite à tenir.
        texte, message_html = _composer_message(Endemie(conduite_a_tenir=conduite), type_notification)

        encodage, longueur, segments = estimer_segments_sms(texte)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== {conduite.code} — {conduite.risque.libelle_fr} "
            f"({'rappel' if options['rappel'] else 'alerte d’entrée en zone'}) ==="
        ))
        self.stdout.write(self.style.MIGRATE_LABEL(
            "\n--- Texte brut (SMS, push, notification locale) ---"
        ))
        self.stdout.write(texte)
        self.stdout.write(
            f"\n[{longueur} caractères, {encodage} → {segments} segment(s) SMS]"
        )
        if encodage == "UCS-2":
            self.stdout.write(self.style.WARNING(
                "Un caractère hors alphabet SMS standard (ex. apostrophe typographique, "
                "« œ », « ê », emoji) double le coût : le remplacer garde le SMS en GSM-7."
            ))
        self.stdout.write(self.style.MIGRATE_LABEL("\n--- HTML (email) ---"))
        self.stdout.write(message_html)

        if options["html_fichier"]:
            chemin = Path(options["html_fichier"]).expanduser()
            chemin.write_text(
                '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
                f"<title>Aperçu {conduite.code}</title></head>"
                '<body style="font-family:sans-serif;max-width:640px;margin:2em auto">'
                f"{message_html}</body></html>",
                encoding="utf-8",
            )
            self.stdout.write(self.style.SUCCESS(f"\nPage HTML écrite : {chemin}"))

    def _lister_conduites(self):
        conduites = ConduiteATenir.objects.select_related("risque").order_by("risque__libelle_fr", "code")
        if not conduites:
            self.stdout.write("Aucune conduite à tenir en base.")
            return
        self.stdout.write("Conduites à tenir disponibles (code — risque) :")
        for conduite in conduites:
            self.stdout.write(f"  {conduite.code} — {conduite.risque.libelle_fr}")
