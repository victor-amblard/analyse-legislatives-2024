"""
Couche de présentation : palette, mise en forme, graphiques.

Aucun module ici n'a de dépendance à Streamlit — ils restent utilisables depuis
les notebooks. Le texte de méthodologie qui vivait dans `methodology` a été
supprimé avec l'onglet du même nom : le billet en est désormais la seule source.
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
