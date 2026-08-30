"""Widget de formulaire pour éditer un champ texte "rgb(r,g,b)" (cf.
risks.colors) via une palette de couleur native du navigateur, plutôt qu'en
tapant la chaîne à la main.

Le champ modèle (`ConduiteATenir.couleur`, `Risque.couleur_legende`) reste un
CharField texte au format "rgb(r,g,b)" — inchangé, car `risks.colors` et
`risks.views.build_risk_map_geojson` en dépendent. Seule la façon de le
saisir dans l'admin change.
"""

from django import forms

from .colors import parse_rgb


def _rgb_to_hex(value):
    rgb = parse_rgb(value)
    if rgb is None:
        return "#000000"
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _hex_to_rgb_css(hex_value):
    if not hex_value:
        return None
    hex_value = hex_value.lstrip("#")
    try:
        r = int(hex_value[0:2], 16)
        g = int(hex_value[2:4], 16)
        b = int(hex_value[4:6], 16)
    except (ValueError, IndexError):
        return None
    return f"rgb({r},{g},{b})"


class NullableColorWidget(forms.MultiWidget):
    """Pastille de couleur (<input type="color">) + case "Aucune couleur".

    Un <input type="color"> natif ne peut pas représenter "pas de couleur" :
    il a toujours une valeur hexadécimale valide. Sans la case à cocher,
    rouvrir puis enregistrer une fiche dont la couleur est vide écrirait
    silencieusement "rgb(0,0,0)" à la place de NULL.
    """

    template_name = "widgets/nullable_color.html"

    def __init__(self, attrs=None):
        widgets = [
            forms.TextInput(attrs={"type": "color"}),
            forms.CheckboxInput(),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if not value:
            return ["#000000", True]
        return [_rgb_to_hex(value), False]


class RGBColorField(forms.MultiValueField):
    widget = NullableColorWidget

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        fields = (
            forms.CharField(required=False),
            forms.BooleanField(required=False),
        )
        super().__init__(fields=fields, require_all_fields=False, **kwargs)

    def compress(self, data_list):
        if not data_list:
            return None
        hex_value, aucune_couleur = data_list
        if aucune_couleur:
            return None
        return _hex_to_rgb_css(hex_value)
