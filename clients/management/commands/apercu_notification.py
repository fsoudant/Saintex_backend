"""
Aperçu de ce qu'un voyageur voit pour une conduite à tenir, sans rien envoyer
ni écrire en base — pour que l'équipe médicale voie comment la mise en forme
de sa recommandation (gras, listes, liens...) est rendue (cf.
saintex-spec-technique.md §5 et §8, texte enrichi).

Depuis octobre 2026 les alertes sont affichées par le TÉLÉPHONE ; la commande
montre donc :

- la notification locale (texte court) ;
- l'écran de détail : la recommandation complète en HTML, telle que transmise
  dans le cache, et sa version texte brut ;
- le SMS court de sauvegarde envoyé par le serveur (option B du §8), avec sa
  taille estimée en segments SMS.

Usage :
    python manage.py apercu_notification                 # liste les conduites
    python manage.py apercu_notification PAL_T1          # aperçu d'une conduite
    python manage.py apercu_notification PAL_T1 --retard-heures 5     # SMS d'une alerte rapportée avec retard
    python manage.py apercu_notification PAL_T1 --html-fichier /tmp/apercu.html
"""

from datetime import timedelta
from html import escape
from pathlib import Path
from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from clients.notifications import composer_sms_alerte
from risks.cache import recommandation_html
from risks.models import ConduiteATenir
from risks.richtext import html_to_text

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
        "Affiche, sans rien envoyer, ce que voit le voyageur pour une conduite à "
        "tenir : notification, écran de détail (HTML et texte brut) et SMS de sauvegarde."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "code", nargs="?",
            help="Code de la conduite à tenir (ex. PAL_T1). Sans code : liste des conduites.",
        )
        parser.add_argument(
            "--retard-heures", type=float, default=0,
            help="Aperçu du SMS d'une alerte rapportée avec ce retard (en heures).",
        )
        parser.add_argument(
            "--html-fichier", metavar="CHEMIN",
            help="Écrit aussi l'écran de détail dans une page HTML à ouvrir dans un navigateur.",
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

        risque = conduite.risque
        detail_html = recommandation_html(conduite, "fr")

        maintenant = timezone.now()
        rapport = SimpleNamespace(
            endemie=SimpleNamespace(conduite_a_tenir=conduite),
            affichee_le=maintenant - timedelta(hours=options["retard_heures"]),
        )
        sms = composer_sms_alerte(rapport, maintenant)
        encodage, longueur, segments = estimer_segments_sms(sms)

        self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== {conduite.code} — {risque.libelle_fr} ==="))

        self.stdout.write(self.style.MIGRATE_LABEL("\n--- Notification affichée par le téléphone ---"))
        self.stdout.write(f"Zone à risque : {risque.libelle_fr}")
        self.stdout.write("Touchez pour lire la conduite à tenir.")

        self.stdout.write(self.style.MIGRATE_LABEL("\n--- Écran de détail (HTML, tel que transmis dans le cache) ---"))
        self.stdout.write(detail_html)

        self.stdout.write(self.style.MIGRATE_LABEL("\n--- Même texte en texte brut ---"))
        self.stdout.write(html_to_text(detail_html))

        legende_retard = f" (alerte rapportée avec {options['retard_heures']:g} h de retard)" if options["retard_heures"] else ""
        self.stdout.write(self.style.MIGRATE_LABEL(f"\n--- SMS de sauvegarde envoyé par le serveur{legende_retard} ---"))
        self.stdout.write(sms)
        self.stdout.write(f"\n[{longueur} caractères, {encodage} → {segments} segment(s) SMS]")
        if encodage == "UCS-2":
            self.stdout.write(self.style.WARNING(
                "Un caractère hors alphabet SMS standard (ex. apostrophe typographique, "
                "« œ », « ê », emoji) double le coût : le remplacer garde le SMS en GSM-7. "
                "Le texte du SMS est composé par le serveur (libellé du risque compris) : "
                "vérifier le libellé du risque."
            ))

        if options["html_fichier"]:
            chemin = Path(options["html_fichier"]).expanduser()
            chemin.write_text(
                '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
                f"<title>Aperçu {conduite.code}</title></head>"
                '<body style="font-family:sans-serif;max-width:640px;margin:2em auto">'
                f"<h3>Zone à risque : {escape(risque.libelle_fr)}</h3>{detail_html}</body></html>",
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
