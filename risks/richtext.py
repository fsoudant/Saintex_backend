"""Texte enrichi des recommandations (cf. saintex-spec-technique.md §8,
décision d'octobre 2026) : mise en forme limitée (gras, italique, taille,
listes) et liens hypertexte vers un site de référence (OMS...) ou le nôtre.

Principes :
- `ConduiteATenir.recommandation_fr/en` stocke du HTML **assaini** (cf.
  `sanitize_html`, appelé à chaque `save()`) : seules les balises de la liste
  blanche ci-dessous survivent, les liens sont limités à http/https/mailto et
  reçoivent `rel="noopener noreferrer"`. L'éditeur de l'admin est confortable,
  mais ce n'est jamais lui qui garantit la sûreté du contenu.
- Les canaux qui ne savent pas afficher de HTML (SMS, push, notification
  locale hors ligne) reçoivent la version texte brut calculée par
  `html_to_text` : liens réduits à « texte (url) », paragraphes et listes
  conservés.
- Les textes existants (saisis en texte brut avant cette évolution) sont
  convertis par `text_to_html`, de façon identique en migration (cf.
  risks/migrations/0009) et à la volée si un texte brut arrive encore.

Tailles : trois niveaux seulement, portés par des balises sémantiques
(`<small>`, `<big>`, `<h3>` pour un titre) plutôt que par des tailles libres
en pixels — cohérent entre email, écran de l'appli et admin, et impossible
à "casser" depuis l'éditeur.
"""

import html
import re
from html.parser import HTMLParser

import nh3

TAGS_AUTORISES = {
    "p", "br", "strong", "b", "em", "i", "u", "a", "ul", "ol", "li", "h3", "small", "big",
}
ATTRIBUTS_AUTORISES = {"a": {"href"}}
SCHEMES_AUTORISES = {"http", "https", "mailto"}

_BALISE_HTML_RE = re.compile(
    r"</?(?:p|br|strong|b|em|i|u|a|ul|ol|li|h[1-6]|small|big|span|div|font)\b", re.IGNORECASE
)
_DIV_RE = re.compile(r"<(/?)div\b[^>]*>", re.IGNORECASE)


def looks_like_html(value):
    """True si `value` contient au moins une balise connue de l'éditeur. Un
    texte brut comme "à moins de <1500 m" n'en contient pas : il sera échappé."""
    return bool(value) and bool(_BALISE_HTML_RE.search(value))


def text_to_html(text):
    """Texte brut -> HTML : échappe les caractères spéciaux, un paragraphe par
    bloc séparé d'une ligne vide, `<br>` pour les retours à la ligne simples."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    blocs = re.split(r"\n\s*\n", text)
    return "".join(
        "<p>" + html.escape(bloc.strip(), quote=False).replace("\n", "<br>") + "</p>"
        for bloc in blocs
    )


def sanitize_html(value):
    """HTML assaini et normalisé pour stockage/envoi ; "" si le contenu est vide
    (ex. l'éditeur laisse `<p><br></p>` quand on efface tout)."""
    value = value or ""
    if not value.strip():
        return ""
    if not looks_like_html(value):
        value = text_to_html(value)
    # Chrome/Safari créent des <div> à chaque Entrée dans un champ éditable si
    # on ne les en empêche pas : ce sont des paragraphes.
    value = _DIV_RE.sub(r"<\1p>", value)
    propre = nh3.clean(
        value,
        tags=TAGS_AUTORISES,
        attributes=ATTRIBUTS_AUTORISES,
        url_schemes=SCHEMES_AUTORISES,
        link_rel="noopener noreferrer",
    ).strip()
    if not html_to_text(propre):
        return ""
    return propre


class _ConvertisseurTexte(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = ""
        self._liens = []  # pile de (href, position de début dans self.out)

    def _saut(self, n):
        """Garantit au moins `n` retours à la ligne en fin de sortie (sans en
        ajouter en tout début de texte)."""
        if not self.out:
            return
        deja = len(self.out) - len(self.out.rstrip("\n"))
        if deja < n:
            self.out += "\n" * (n - deja)

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.out += "\n"
        elif tag in ("p", "h3"):
            self._saut(2)
        elif tag in ("ul", "ol"):
            self._saut(1)
        elif tag == "li":
            self._saut(1)
            self.out += "- "
        elif tag == "a":
            href = dict(attrs).get("href")
            self._liens.append((href, len(self.out)))

    def handle_endtag(self, tag):
        if tag in ("p", "h3"):
            self._saut(2)
        elif tag in ("ul", "ol", "li"):
            self._saut(1)
        elif tag == "a" and self._liens:
            href, debut = self._liens.pop()
            texte_lien = self.out[debut:].strip()
            if href and texte_lien != href:
                self.out += f" ({href})"

    def handle_data(self, data):
        data = re.sub(r"[ \t\r\n\xa0]+", " ", data)
        if not self.out or self.out.endswith("\n"):
            data = data.lstrip(" ")
        self.out += data

    def resultat(self):
        lignes = [ligne.rstrip() for ligne in self.out.split("\n")]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lignes)).strip()


def html_to_text(value):
    """HTML (déjà assaini) -> texte brut pour les canaux sans mise en forme
    (SMS, push, notification locale). Les liens deviennent « texte (url) »,
    sauf si le texte du lien est déjà l'adresse."""
    convertisseur = _ConvertisseurTexte()
    convertisseur.feed(value or "")
    convertisseur.close()
    return convertisseur.resultat()
