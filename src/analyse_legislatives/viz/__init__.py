"""
Couche de présentation : palette, mise en forme, graphiques.

Aucun module ici n'a de dépendance à Streamlit — ils restent utilisables depuis
les notebooks. Le texte de méthodologie qui vivait dans `methodology` a été
supprimé avec l'onglet du même nom : le billet en est désormais la seule source.
"""

from analyse_legislatives.viz.formatting import (
    DISPLAY_NAMES,
    INTERVAL_LEVEL,
    display_name,
    format_interval,
    format_number,
    interval_bounds,
)
from analyse_legislatives.viz.palette import (
    LABEL_COLORS_DARK,
    LABEL_COLORS_LIGHT,
    NEUTRAL_GREY,
    NUANCE_COLORS,
    POLITICAL_FAMILY_COLORS,
    color_for,
    label_color_for,
)

__all__ = [
    "DISPLAY_NAMES",
    "INTERVAL_LEVEL",
    "LABEL_COLORS_DARK",
    "LABEL_COLORS_LIGHT",
    "NEUTRAL_GREY",
    "NUANCE_COLORS",
    "POLITICAL_FAMILY_COLORS",
    "color_for",
    "display_name",
    "format_interval",
    "format_number",
    "interval_bounds",
    "label_color_for",
]
