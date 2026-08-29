"""Couleurs des partis. Aucune logique, uniquement des constantes."""

from analyse_legislatives.parties import PoliticalFamily

POLITICAL_FAMILY_COLORS: dict[str, str] = {
    PoliticalFamily.RNx: "#0b5394",
    PoliticalFamily.DIV: "#8e7cc3",
    PoliticalFamily.LR: "#0086ff",
    PoliticalFamily.NFPx: "#e06666",
    PoliticalFamily.ENSx: "#f1c232",
    # Reprises telles quelles de NUANCE_COLORS : DVG et DVD ont leur propre teinte
    # depuis toujours dans les visualisations de nuances, c'est leur agrégation
    # dans NFP+ / LR qui les masquait.
    PoliticalFamily.DVG: "#ea9999",
    PoliticalFamily.DVD: "#9fc5e8",
}
"""Couleur par grande tendance politique (7 blocs, voir
config/party_families.json)."""

NUANCE_COLORS: dict[str, str] = {
    "EXG": "#ac2929",
    "RN": "#0b5394",
    "LR": "#0086ff",
    "UG": "#e06666",
    "DSV": "#0b5394",
    "ENS": "#f1c232",
    "EXD": "#3470a7",
    "DIV": "#8e7cc3",
    "ECO": "#8fce00",
    "DVD": "#9fc5e8",
    "REC": "#0b5394",
    "UXD": "#0b5394",
    "DVG": "#ea9999",
    "UDI": "#ffe599",
    "REG": "#a64d79",
    "DVC": "#ffe599",
    "HOR": "#ffe599",
    "COM": "#cc0000",
    "SOC": "#f0b7b7",
    "FI": "#cc0000",
    "VEC": "#8fce00",
    "RDG": "#8fce00",
}
"""Couleur par nuance politique brute (colonne CodNuaCand des données 1er tour),
utilisée par les notebooks de prétraitement, avant regroupement en familles."""

NEUTRAL_GREY = "#999999"
"""Repli pour toute clé absente des tables ci-dessus."""


def color_for(party) -> str:
    return POLITICAL_FAMILY_COLORS.get(party, NEUTRAL_GREY)
