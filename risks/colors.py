import re

_RGB_RE = re.compile(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")


def parse_rgb(value):
    """'rgb(255,200,0)' -> (255, 200, 0). None si absent/illisible."""
    if not value:
        return None
    m = _RGB_RE.match(value.strip())
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def average_rgb(colors):
    """Moyenne d'une liste de tuples (r,g,b), en ignorant les None.
    Retourne None si aucune couleur exploitable.
    """
    usable = [c for c in colors if c]
    if not usable:
        return None
    n = len(usable)
    return (
        sum(c[0] for c in usable) // n,
        sum(c[1] for c in usable) // n,
        sum(c[2] for c in usable) // n,
    )


def to_css(rgb):
    if rgb is None:
        return None
    return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"
