# Generated manually (pas de shell disponible sur cette machine).
#
# Cf. saintex-spec-technique.md §8 : décision d'octobre 2026 — les
# recommandations (ConduiteATenir.recommandation_fr/en) deviennent du texte
# enrichi (HTML limité : gras, italique, taille, listes, liens hypertexte).
# Aucun changement de schéma (les champs restent des TextField) : cette
# migration de données convertit les textes existants, saisis en texte brut,
# en HTML (échappement + paragraphes), pour qu'ils s'affichent correctement
# avec leurs retours à la ligne dans l'éditeur, l'email et l'appli.
#
# Les fonctions sont volontairement recopiées ici (équivalent de
# risks.richtext.text_to_html / looks_like_html) : une migration ne doit pas
# dépendre de code applicatif susceptible d'évoluer.

import html
import re

from django.db import migrations

_BALISE_HTML_RE = re.compile(
    r"</?(?:p|br|strong|b|em|i|u|a|ul|ol|li|h[1-6]|small|big|span|div|font)\b", re.IGNORECASE
)


def _text_to_html(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    blocs = re.split(r"\n\s*\n", text)
    return "".join(
        "<p>" + html.escape(bloc.strip(), quote=False).replace("\n", "<br>") + "</p>"
        for bloc in blocs
    )


def convertir_en_html(apps, schema_editor):
    ConduiteATenir = apps.get_model("risks", "ConduiteATenir")
    for conduite in ConduiteATenir.objects.all():
        modifications = {}
        for champ in ("recommandation_fr", "recommandation_en"):
            valeur = getattr(conduite, champ)
            if valeur and not _BALISE_HTML_RE.search(valeur):
                modifications[champ] = _text_to_html(valeur)
        if modifications:
            # update() plutôt que save() : le modèle historique n'a pas le
            # save() applicatif, et on ne touche qu'aux champs convertis.
            ConduiteATenir.objects.filter(pk=conduite.pk).update(**modifications)


class Migration(migrations.Migration):

    dependencies = [
        ('risks', '0008_recommandation_unique'),
    ]

    operations = [
        # Pas de retour arrière automatique : le HTML produit reste un texte
        # valide pour l'ancien code (affiché tel quel), sans perte de contenu.
        migrations.RunPython(convertir_en_html, migrations.RunPython.noop),
    ]
