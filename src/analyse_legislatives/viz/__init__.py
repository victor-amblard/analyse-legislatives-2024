"""
Couche de présentation : palette, mise en forme, graphiques, texte de
méthodologie.

`charts` et `formatting` n'ont aucune dépendance à Streamlit — ils restent
utilisables depuis les notebooks. `methodology` est la seule exception (c'est du
texte d'interface), et n'est donc pas ré-exporté ici.
"""

from analyse_legislatives.viz.formatting import (
    INTERVAL_LEVEL,
    format_interval,
    format_number,
    interval_bounds,
)
from analyse_legislatives.viz.palette import (
    NEUTRAL_GREY,
    NUANCE_COLORS,
    POLITICAL_FAMILY_COLORS,
    color_for,
)

__all__ = [
    "INTERVAL_LEVEL",
    "NEUTRAL_GREY",
    "NUANCE_COLORS",
    "POLITICAL_FAMILY_COLORS",
    "color_for",
    "format_interval",
    "format_number",
    "interval_bounds",
]
