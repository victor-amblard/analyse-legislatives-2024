"""Colours and small SVG helpers shared by explanatory illustrations."""

from analyse_legislatives.parties import NON_EXPRIMES
from analyse_legislatives.viz.palette import POLITICAL_FAMILY_COLORS

ABS_COLOR = "#8a9099"


def party_colour(party) -> str:
    if party == NON_EXPRIMES or party == "NON_EXPRIMES":
        return ABS_COLOR
    return POLITICAL_FAMILY_COLORS.get(party, "#999999")


def readable_ink(hex_colour: str) -> str:
    values = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in values
    ]
    luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    return "#12141a" if luminance > 0.42 else "#ffffff"


def theme_style() -> str:
    """`.accent` reprend le teal de marque du site (`--accent` dans
    `global.css`), pas une couleur choisie pour cette seule figure : une
    illustration qui invente sa propre teinte à chaque fois finit par ressembler
    à un patchwork de palettes plutôt qu'à des pages du même site."""
    return """<style>
    .surface{fill:#fbfbfc}.ink{fill:#16181d}.muted{fill:#5a616e}
    .rule{stroke:#dfe2e8}.grid{stroke:#e8eaee}.frame{fill:none;stroke:#c9cdd5}
    .accent{fill:#1f6f6b}.accent-line{stroke:#1f6f6b}
    @media(prefers-color-scheme:dark){.surface{fill:#14161a}.ink{fill:#e9eaee}
    .muted{fill:#9aa2b1}.rule{stroke:#3a3f49}.grid{stroke:#292d35}.frame{stroke:#555c69}
    .accent{fill:#5cb8b1}.accent-line{stroke:#5cb8b1}}
    text{font-family:Inter,ui-sans-serif,system-ui,sans-serif}
    </style>"""
