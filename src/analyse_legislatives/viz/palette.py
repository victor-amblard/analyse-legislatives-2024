"""Couleurs des partis et neutres de thème. Aucune logique, ou presque."""

from dataclasses import dataclass

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

# Les couleurs historiques ci-dessus fonctionnent bien comme aplats, mais les
# plus claires disparaissent en traits fins sur fond blanc et le bleu RN+ se
# perd sur fond sombre. Ces variantes conservent les mêmes teintes politiques
# tout en assurant un contraste d'au moins 3:1 avec le fond des graphiques.
CHART_COLORS_LIGHT: dict[str, str] = {
    PoliticalFamily.RNx: "#0b5394",
    PoliticalFamily.DIV: "#7055a5",
    PoliticalFamily.LR: "#006dcc",
    PoliticalFamily.NFPx: "#c94f4f",
    PoliticalFamily.ENSx: "#8a6800",
    PoliticalFamily.DVG: "#a94f57",
    PoliticalFamily.DVD: "#527fa8",
}

CHART_COLORS_DARK: dict[str, str] = {
    PoliticalFamily.RNx: "#5b9bd5",
    PoliticalFamily.DIV: "#b0a0df",
    PoliticalFamily.LR: "#55aaff",
    PoliticalFamily.NFPx: "#ef8585",
    PoliticalFamily.ENSx: "#f4cf5b",
    PoliticalFamily.DVG: "#f0aaaa",
    PoliticalFamily.DVD: "#afd3f3",
}

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

LABEL_COLORS_LIGHT: dict[str, str] = {
    PoliticalFamily.RNx: "#0b5394",
    PoliticalFamily.DIV: "#6f55a5",
    PoliticalFamily.LR: "#0069c0",
    PoliticalFamily.NFPx: "#c0392b",
    PoliticalFamily.ENSx: "#a06a12",
    PoliticalFamily.DVG: "#b05a62",
    PoliticalFamily.DVD: "#456f97",
}
"""Couleurs des NOMS de partis, lisibles comme texte.

Les couleurs de marque ne conviennent pas à du texte : le jaune d'`ENS+`
n'atteint que 1,7:1 sur fond clair, le bleu pâle de `DVD` 1,8:1, là où un
libellé de cette taille demande 4,5:1. Ces variantes conservent la teinte du
parti au contraste requis (4,6 à 7,8:1).

`ENS+` fait exception : assombrir son jaune donne un brun olive qui ne se
reconnaît plus. Sa teinte est donc décalée vers l'ambre, qui reste identifiable
une fois foncé."""

LABEL_COLORS_DARK: dict[str, str] = {
    PoliticalFamily.RNx: "#7fb4e4",
    PoliticalFamily.DIV: "#b9a6e8",
    PoliticalFamily.LR: "#5fb0ff",
    PoliticalFamily.NFPx: "#f08a8a",
    PoliticalFamily.ENSx: "#f0bf5e",
    PoliticalFamily.DVG: "#eda9ae",
    PoliticalFamily.DVD: "#a8cdee",
}
"""Mêmes teintes éclaircies pour le thème sombre (7,8 à 11,4:1)."""

NEUTRAL_GREY = "#999999"
"""Repli pour toute clé absente des tables ci-dessus."""


def color_for(party) -> str:
    return POLITICAL_FAMILY_COLORS.get(party, NEUTRAL_GREY)


def label_color_for(party, *, dark: bool = False) -> str:
    """Couleur d'un nom de parti affiché en texte."""
    table = LABEL_COLORS_DARK if dark else LABEL_COLORS_LIGHT
    return table.get(party, NEUTRAL_GREY)


def chart_color_for(party, *, dark: bool = False) -> str:
    """Couleur de parti suffisamment contrastée pour un trait ou un point."""
    palette = CHART_COLORS_DARK if dark else CHART_COLORS_LIGHT
    return palette.get(party, NEUTRAL_GREY)


def chart_palette(*, dark: bool = False) -> dict[str, str]:
    """Palette complète destinée aux échelles catégorielles des graphiques."""
    return CHART_COLORS_DARK if dark else CHART_COLORS_LIGHT


@dataclass(frozen=True)
class ChartTheme:
    """Neutres d'un graphique, pour le thème actif du navigateur.

    Les teintes de parti gardent la même identité dans les deux thèmes, avec une
    luminosité adaptée dans ``CHART_COLORS_*``. Les neutres doivent eux aussi
    suivre le fond — une ligne d'égalité noire disparaît en thème sombre.

    Ces valeurs sont posées AU NIVEAU DES MARQUES. C'est ce qui les rend
    nécessaires : le thème Vega que Streamlit injecte n'agit que sur `config`,
    et en Vega-Lite une propriété de marque l'emporte toujours sur `config`.
    Streamlit ne peut donc pas corriger un `color="black"` écrit ici.
    """

    ink: str
    """Trait de premier plan : lignes de repère, losange du scénario médian."""

    halo: str
    """Liseré autour des points superposés — c'est la couleur du FOND, pas une
    couleur d'encre : il sert à détacher un point de ses voisins."""

    rule: str
    """Repères secondaires, plus discrets que `ink`."""

    muted: str
    """Étiquettes annexes (graduations des repères obliques)."""


CHART_THEME_LIGHT = ChartTheme(
    ink="#16181d", halo="#ffffff", rule="#c7c7c7", muted="#888888"
)
CHART_THEME_DARK = ChartTheme(
    ink="#e9eaee", halo="#0e1117", rule="#4a505c", muted="#aeb4c0"
)


def chart_theme(dark: bool = False) -> ChartTheme:
    """Neutres du thème demandé. `dark` vient de `st.context.theme`."""
    return CHART_THEME_DARK if dark else CHART_THEME_LIGHT
