"""Illustrative vote flows for district 0101."""

from xml.sax.saxutils import escape

from analyse_legislatives.data import load_full_results
from analyse_legislatives.parties import (
    SPECTRUM_ORDER,
    label as party_label,
)
from analyse_legislatives.publication.illustrations._shared import ABS_COLOR
from analyse_legislatives.viz.palette import POLITICAL_FAMILY_COLORS


DISTRICT_ID = "0101"
SOURCES = ("LR", "RN+", "NFP+", "ENS+", "NON_EXPRIMES")
TARGETS = ("LR", "RN+", "NON_EXPRIMES")
EXAMPLE_RATES = {
    "LR": (0.96, 0.00, 0.04),
    "RN+": (0.00, 0.96, 0.04),
    "NFP+": (0.62, 0.25, 0.13),
    "ENS+": (0.71, 0.19, 0.10),
    "NON_EXPRIMES": (0.05, 0.05, 0.90),
}


def _integer_flows(total: int, rates: tuple[float, ...]) -> tuple[int, ...]:
    """Round displayed flows while preserving the source total."""
    first = tuple(round(total * rate) for rate in rates[:-1])
    return (*first, total - sum(first))


def sankey_flows():
    """Return the data-backed pools and illustrative flows used in the text."""
    district = next(
        district
        for district in load_full_results().districts
        if district.circonscription.id == DISTRICT_ID
    )
    label_to_family = {party_label(party): party for party in SPECTRUM_ORDER}
    pools = district.available_vote_pools_by_party()
    totals = {
        source: (
            district.non_expressed
            if source == "NON_EXPRIMES"
            else pools[label_to_family[source]]
        )
        for source in SOURCES
    }
    flows = {
        source: _integer_flows(totals[source], EXAMPLE_RATES[source])
        for source in SOURCES
    }
    return totals, flows


def build_prior_sankey_svg() -> str:
    source_totals, flows = sankey_flows()
    label_to_family = {party_label(party): party for party in SPECTRUM_ORDER}

    def colour(name: str) -> str:
        if name == "NON_EXPRIMES":
            return ABS_COLOR
        return POLITICAL_FAMILY_COLORS[label_to_family[name]]

    width, height = 760, 440
    top, bottom, node_width, gap = 72, 32, 13, 8
    left_x, right_x = 132, width - 176
    target_totals = {
        target: sum(flows[source][index] for source in SOURCES)
        for index, target in enumerate(TARGETS)
    }
    total = sum(source_totals.values())
    available = height - top - bottom - gap * (max(len(SOURCES), len(TARGETS)) - 1)
    scale = available / total

    def stack(names, totals):
        positions, y = {}, top
        for name in names:
            node_height = max(2.0, totals[name] * scale)
            positions[name] = (y, node_height)
            y += node_height + gap
        return positions

    left = stack(SOURCES, source_totals)
    right = stack(TARGETS, target_totals)
    parts = [
        """<style>
    .surface{fill:#fbfbfc}.ink{fill:#16181d}.muted{fill:#5a616e}
    @media(prefers-color-scheme:dark){.surface{fill:#14161a}.ink{fill:#e9eaee}.muted{fill:#9aa2b1}}
    text{font-family:ui-sans-serif,-apple-system,'Segoe UI',Roboto,sans-serif}
    </style>""",
        f'<rect class="surface" width="{width}" height="{height}"/>',
        '<text class="ink" x="16" y="26" font-size="13" font-weight="600">Un tirage des flux de voix dans la circonscription 0101</text>',
        '<text class="muted" x="16" y="44" font-size="11">Les largeurs correspondent au nombre de voix obtenu avec les taux de report de l’exemple.</text>',
        f'<text class="muted" x="16" y="{top - 12}" font-size="10" letter-spacing="0.06em">PREMIER TOUR</text>',
        f'<text class="muted" x="{right_x + node_width}" y="{top - 12}" font-size="10" letter-spacing="0.06em" text-anchor="end">SECOND TOUR</text>',
    ]

    left_cursor = {name: left[name][0] for name in SOURCES}
    right_cursor = {name: right[name][0] for name in TARGETS}
    ribbons = []
    for source in SOURCES:
        for target_index, target in enumerate(TARGETS):
            value = flows[source][target_index]
            if value <= 0:
                continue
            ribbon_height = value * scale
            ribbons.append(
                (
                    value,
                    source,
                    left_cursor[source],
                    right_cursor[target],
                    ribbon_height,
                )
            )
            left_cursor[source] += ribbon_height
            right_cursor[target] += ribbon_height
    for _, source, left_y, right_y, ribbon_height in sorted(ribbons, reverse=True):
        x0, x1 = left_x + node_width, right_x
        middle = (x0 + x1) / 2
        path = (
            f"M {x0} {left_y:.1f} C {middle} {left_y:.1f} {middle} {right_y:.1f} {x1} {right_y:.1f} "
            f"L {x1} {right_y + ribbon_height:.1f} C {middle} {right_y + ribbon_height:.1f} "
            f"{middle} {left_y + ribbon_height:.1f} {x0} {left_y + ribbon_height:.1f} Z"
        )
        parts.append(f'<path d="{path}" fill="{colour(source)}" opacity="0.42"/>')

    def spread(names, positions):
        labels, previous = {}, None
        for name in names:
            y, node_height = positions[name]
            centre = y + node_height / 2
            if previous is not None and centre - previous < 28:
                centre = previous + 28
            labels[name], previous = centre, centre
        return labels

    for names, x, anchor, positions, totals in (
        (SOURCES, left_x, "end", left, source_totals),
        (TARGETS, right_x, "start", right, target_totals),
    ):
        label_positions = spread(names, positions)
        for name in names:
            y, node_height = positions[name]
            label_y = label_positions[name]
            text_x = x - 10 if anchor == "end" else x + node_width + 10
            parts.append(
                f'<rect x="{x}" y="{y:.1f}" width="{node_width}" height="{node_height:.1f}" rx="2.5" fill="{colour(name)}"/>'
            )
            if abs(label_y - (y + node_height / 2)) > 1.5:
                start_x = x - 3 if anchor == "end" else x + node_width + 3
                end_x = text_x + (3 if anchor == "end" else -3)
                parts.append(
                    f'<line x1="{start_x}" y1="{y + node_height / 2:.1f}" x2="{end_x}" y2="{label_y:.1f}" stroke="{colour(name)}" stroke-width="0.9" opacity="0.8"/>'
                )
            displayed_total = f"{totals[name]:,}".replace(",", "\u202f")
            parts.extend(
                [
                    f'<text class="ink" x="{text_x}" y="{label_y - 1:.1f}" font-size="11.5" font-weight="600" text-anchor="{anchor}">{escape(name)}</text>',
                    f'<text class="muted" x="{text_x}" y="{label_y + 11:.1f}" font-size="10" text-anchor="{anchor}">{displayed_total} voix</text>',
                ]
            )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Flux de voix illustratifs dans la circonscription 0101.">'
        f'{"".join(parts)}</svg>\n'
    )
