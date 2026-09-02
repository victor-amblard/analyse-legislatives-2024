"""Preference-ordering diagram used to explain the ordinal prior."""

from xml.sax.saxutils import escape

from analyse_legislatives.config import DEFAULT_TRANSFER_ORDERINGS
from analyse_legislatives.parties import SPECTRUM_ORDER, label as party_label
from analyse_legislatives.publication.illustrations._shared import (
    party_colour,
    readable_ink,
)


def build_orderings_svg() -> str:
    sources = [party for party in SPECTRUM_ORDER if party in DEFAULT_TRANSFER_ORDERINGS]
    chip_h, chip_gap, tier_gap = 24, 5, 26
    row_gap, pad_l, pad_t, pad_r = 40, 74, 52, 20

    def chip_width(text: str) -> float:
        return max(38, len(text) * 6.6 + 22)

    rows, widest, y = [], 0.0, pad_t
    for source in sources:
        x: float = pad_l
        chips, separators = [], []
        for tier_index, tier in enumerate(DEFAULT_TRANSFER_ORDERINGS[source]):
            if tier_index:
                separators.append(x + tier_gap / 2)
                x += tier_gap
            for destination_index, destination in enumerate(tier):
                if destination_index:
                    x += chip_gap
                text = party_label(destination)
                width = chip_width(text)
                chips.append((x, width, text, destination, len(tier) > 1))
                x += width
        rows.append((source, y, chips, separators))
        widest = max(widest, x)
        y += chip_h + row_gap

    footnote = "Groupes de partis soulignés : le modèle n'ordonne pas ces partis et tire un ordre au hasard à chaque simulation."
    width = max(widest, pad_l + len(footnote) * 5.4) + pad_r
    height = y - row_gap + 34
    parts = [
        """<style>
    .surface{fill:#fbfbfc}.ink{fill:#16181d}.muted{fill:#5a616e}
    .sep{stroke:#b9bec7}.tie{stroke:#c8ccd3}
    @media(prefers-color-scheme:dark){.surface{fill:#14161a}.ink{fill:#e9eaee}
    .muted{fill:#9aa2b1}.sep{stroke:#555c67}.tie{stroke:#3a4049}}
    text{font-family:ui-sans-serif,-apple-system,'Segoe UI',Roboto,sans-serif}
    </style>""",
        f'<rect class="surface" width="{width:.0f}" height="{height:.0f}"/>',
        '<text class="muted" x="8" y="24" font-size="10.5" letter-spacing="0.07em">SOURCE</text>',
        f'<text class="muted" x="{pad_l}" y="24" font-size="10.5" letter-spacing="0.07em">Transferts vers... (du plus au moins préféré)</text>',
    ]

    for source, row_y, chips, separators in rows:
        centre_y = row_y + chip_h / 2
        parts.append(
            f'<text class="ink" x="8" y="{centre_y + 4:.1f}" font-size="12" '
            f'font-weight="600">{escape(party_label(source))}</text>'
        )
        for separator_x in separators:
            parts.append(
                f'<text class="sep muted" x="{separator_x:.1f}" y="{centre_y + 4:.1f}" '
                f'font-size="13" text-anchor="middle" font-weight="600">&#8827;</text>'
            )
        tied = [chip for chip in chips if chip[4]]
        groups: list[list[tuple]] = []
        for chip in tied:
            if (
                groups
                and abs(groups[-1][-1][0] + groups[-1][-1][1] + chip_gap - chip[0])
                < 1.5
            ):
                groups[-1].append(chip)
            else:
                groups.append([chip])
        for group in groups:
            x0, x1 = group[0][0], group[-1][0] + group[-1][1]
            parts.append(
                f'<line class="tie" x1="{x0:.1f}" y1="{row_y + chip_h + 5:.1f}" '
                f'x2="{x1:.1f}" y2="{row_y + chip_h + 5:.1f}" stroke-width="2" '
                f'stroke-linecap="round"/>'
            )
        for x, chip_w, text, destination, _ in chips:
            fill = party_colour(destination)
            parts.extend(
                [
                    f'<rect x="{x:.1f}" y="{row_y}" width="{chip_w:.1f}" height="{chip_h}" rx="5" fill="{fill}"/>',
                    f'<text x="{x + chip_w / 2:.1f}" y="{centre_y + 4:.1f}" font-size="11.5" '
                    f'font-weight="600" text-anchor="middle" fill="{readable_ink(fill)}">{escape(text)}</text>',
                ]
            )
    parts.append(
        f'<text class="muted" x="{pad_l}" y="{height - 10:.1f}" font-size="10.5">{footnote}</text>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'role="img" aria-label="Declared transfer preference ordering for each source party.">'
        f'{"".join(parts)}</svg>\n'
    )
