"""
Vérification en LECTURE SEULE des conduites à tenir, avant l'évolution
« Modulation » (fin octobre 2026, cf. saintex-spec-technique.md §7 et §8).

Contrôle, pour chaque `ConduiteATenir` :
- la **période** (saison_mois_debut / saison_mois_fin), extraite à l'origine du
  texte de la recommandation : renseignée si le texte cite des mois, et
  cohérente avec la plage « de X à Y » trouvée dans le texte ;
- la **modulation** (facteurs_de_risque_fr/en) : renseignée ;
- la recommandation (fr/en) : renseignée.

N'écrit rien en base. Usage :

    python manage.py verifier_conduites               # synthèse + anomalies
    python manage.py verifier_conduites --tout        # + toutes les conduites
    python manage.py verifier_conduites --csv conduites.csv   # export complet
"""

import csv
import html
import re

from django.core.management.base import BaseCommand
from django.db.models import Count

from risks.models import ConduiteATenir

MOIS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
NOMS = "|".join(sorted(MOIS, key=len, reverse=True))
RE_MOIS = re.compile(rf"(?<!\w)({NOMS})(?!\w)", re.IGNORECASE)
# « d'août à novembre », « de juin à septembre », « du mois de mai à octobre »...
RE_PLAGE = re.compile(
    rf"(?<!\w)(?:de|d['’]|du)\s*(?:mois\s+(?:de\s+|d['’])?)?({NOMS})\s+"
    rf"(?:à|a|au|jusqu['’]à|jusqu['’]au)\s+(?:fin\s+|début\s+|debut\s+)?({NOMS})(?!\w)",
    re.IGNORECASE,
)


def _texte(valeur):
    """Texte brut d'un champ éventuellement en HTML."""
    return html.unescape(re.sub(r"<[^>]+>", " ", valeur or ""))


class Command(BaseCommand):
    help = "Vérifie (lecture seule) périodes, modulations et recommandations des conduites à tenir."

    def add_arguments(self, parser):
        parser.add_argument("--tout", action="store_true", help="Afficher aussi les conduites sans anomalie.")
        parser.add_argument("--csv", metavar="FICHIER", help="Exporter toutes les conduites dans un fichier CSV.")

    def handle(self, *args, **options):
        conduites = (
            ConduiteATenir.objects.select_related("risque")
            .annotate(nb_endemies=Count("endemies"))
            .order_by("risque_id", "code")
        )

        lignes = []
        for c in conduites:
            texte = _texte(c.recommandation_fr)
            mois_cites = sorted({MOIS[m.lower()] for m in RE_MOIS.findall(texte)})
            plage = RE_PLAGE.search(texte)
            attendu = (MOIS[plage.group(1).lower()], MOIS[plage.group(2).lower()]) if plage else None
            saison = (c.saison_mois_debut, c.saison_mois_fin)
            saison_renseignee = saison != (None, None)

            anomalies = []
            if not saison_renseignee and mois_cites:
                anomalies.append(f"PÉRIODE ABSENTE alors que le texte cite des mois ({mois_cites})")
            if saison_renseignee and attendu and attendu != saison:
                anomalies.append(f"PÉRIODE DIFFÉRENTE du texte : stockée {saison}, texte {attendu}")
            if saison_renseignee and not mois_cites:
                anomalies.append("période renseignée mais aucun mois cité dans la recommandation (saisie manuelle ?)")
            if not (c.facteurs_de_risque_fr or "").strip():
                anomalies.append("MODULATION fr VIDE")
            elif not (c.facteurs_de_risque_en or "").strip():
                anomalies.append("modulation en vide")
            if not texte.strip():
                anomalies.append("RECOMMANDATION fr vide")
            elif not _texte(c.recommandation_en).strip():
                anomalies.append("recommandation en vide")

            lignes.append({
                "code": c.code,
                "risque": c.risque_id,
                "nb_endemies": c.nb_endemies,
                "periode_debut": c.saison_mois_debut,
                "periode_fin": c.saison_mois_fin,
                "mois_cites_dans_texte": " ".join(map(str, mois_cites)),
                "plage_detectee_dans_texte": f"{attendu[0]}-{attendu[1]}" if attendu else "",
                "modulation_fr": (c.facteurs_de_risque_fr or "").strip(),
                "modulation_en": (c.facteurs_de_risque_en or "").strip(),
                "anomalies": " | ".join(anomalies),
            })

        if options["csv"]:
            with open(options["csv"], "w", newline="", encoding="utf-8-sig") as f:
                ecrivain = csv.DictWriter(f, fieldnames=list(lignes[0].keys()) if lignes else ["code"])
                ecrivain.writeheader()
                ecrivain.writerows(lignes)
            self.stdout.write(f"Export CSV : {options['csv']} ({len(lignes)} lignes)\n")

        total = len(lignes)
        avec_periode = sum(1 for l in lignes if l["periode_debut"] is not None)
        avec_modulation = sum(1 for l in lignes if l["modulation_fr"])
        en_anomalie = [l for l in lignes if l["anomalies"]]

        self.stdout.write(f"{total} conduites à tenir")
        self.stdout.write(f"  avec période renseignée  : {avec_periode}")
        self.stdout.write(f"  avec modulation fr       : {avec_modulation}")
        self.stdout.write(f"  avec au moins une anomalie : {len(en_anomalie)}\n")

        a_afficher = lignes if options["tout"] else en_anomalie
        for l in a_afficher:
            periode = f"{l['periode_debut']}→{l['periode_fin']}" if l["periode_debut"] is not None else "—"
            self.stdout.write(
                f"[{l['risque']}] {l['code']}  (endémies : {l['nb_endemies']}, période : {periode})"
            )
            if l["modulation_fr"]:
                self.stdout.write(f"    modulation : {l['modulation_fr'][:100]}")
            if l["anomalies"]:
                for anomalie in l["anomalies"].split(" | "):
                    self.stdout.write(f"    ⚠ {anomalie}")
