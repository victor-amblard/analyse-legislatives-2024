"""Prior-predictive vote-flow Sankey for ENS+/RN+ runoffs."""

from xml.sax.saxutils import escape

import numpy as np

from analyse_legislatives.config import DEFAULT_SEED
from analyse_legislatives.data import load_full_results
from analyse_legislatives.parties import (
    NON_EXPRIMES,
    SPECTRUM_ORDER,
    label as party_label,
)
from analyse_legislatives.publication.illustrations._shared import ABS_COLOR
from analyse_legislatives.viz.palette import POLITICAL_FAMILY_COLORS

BLOG_DUEL = ("ENS+", "RN+")
SANKEY_DRAWS = 240


def sankey_flows(duel_labels=BLOG_DUEL, n_draws=SANKEY_DRAWS, seed=DEFAULT_SEED):
    """Return prior-predictive flow summaries for districts with this runoff."""
    from analyse_legislatives.models import build as build_model
    from analyse_legislatives.transfers import normalize_for_district

    label_to_family = {party_label(party): party for party in SPECTRUM_ORDER}
    districts = load_full_results().districts
    qualified = {label_to_family[label] for label in duel_labels}
    selected_indices = [
        index
        for index, district in enumerate(districts)
        if {
            party
            for party, votes in district.competing_parties_results.items()
            if votes > 0
        }
        == qualified
    ]
    selected = [districts[index] for index in selected_indices]

    present = {
        party
        for district in selected
        for party, votes in district.eliminated_parties_results.items()
        if votes > 0 and party not in qualified
    }
    volume = {
        party: sum(
            district.eliminated_parties_results.get(party, 0) for district in selected
        )
        for party in present
    }
    source_families = sorted(present, key=volume.get, reverse=True) + [NON_EXPRIMES]
    sources = [
        "NON_EXPRIMES" if party is NON_EXPRIMES else party_label(party)
        for party in source_families
    ]
    target_families = [label_to_family[label] for label in duel_labels] + [NON_EXPRIMES]
    targets = [*duel_labels, "NON_EXPRIMES"]

    model = build_model(seed=seed)
    samples = np.zeros((n_draws, len(sources), len(targets)))
    for draw_index in range(n_draws):
        parameters = model.draw_simulation()
        matrices = model.sample_transfer_matrices(districts, parameters)
        for district_index, district in zip(selected_indices, selected):
            matrix = normalize_for_district(
                matrices[district_index], district, parameters.tilt
            )
            pools = dict(district.eliminated_parties_results)
            pools[NON_EXPRIMES] = district.non_expressed
            for source_index, source in enumerate(source_families):
                pool = pools.get(source, 0)
                if pool <= 0:
                    continue
                row = matrix.rates.get(source, {})
                for target_index, target in enumerate(target_families):
                    samples[draw_index, source_index, target_index] += pool * row.get(
                        target, 0.0
                    )

    median = np.median(samples, axis=0)
    low, high = np.percentile(samples, [5, 95], axis=0)
    flows = {
        source: [
            (
                float(median[source_index, target_index]),
                float(low[source_index, target_index]),
                float(high[source_index, target_index]),
            )
            for target_index in range(len(targets))
        ]
        for source_index, source in enumerate(sources)
    }
    return sources, targets, flows, len(selected)


def build_prior_sankey_svg() -> str:
    sources, targets, flows, district_count = sankey_flows()
    label_to_family = {party_label(party): party for party in SPECTRUM_ORDER}

    def colour(name: str) -> str:
        if name == "NON_EXPRIMES":
            return ABS_COLOR
        return POLITICAL_FAMILY_COLORS[label_to_family[name]]

    width, height = 760, 470
    top, bottom, node_width, gap = 74, 44, 13, 7
    left_x, right_x = 132, width - 176
    source_totals = {
        source: sum(flow[0] for flow in flows[source]) for source in sources
    }
    target_totals = {
        target: sum(flows[source][index][0] for source in sources)
        for index, target in enumerate(targets)
    }
    total = sum(source_totals.values())
    available = height - top - bottom - gap * (max(len(sources), len(targets)) - 1)
    scale = available / total

    def stack(names, totals):
        positions, y = {}, top
        for name in names:
            node_height = max(2.0, totals[name] * scale)
            positions[name] = (y, node_height)
            y += node_height + gap
        return positions

    left, right = stack(sources, source_totals), stack(targets, target_totals)
    parts = [
        """<style>
    .surface{fill:#fbfbfc}.ink{fill:#16181d}.muted{fill:#5a616e}
    @media(prefers-color-scheme:dark){.surface{fill:#14161a}.ink{fill:#e9eaee}.muted{fill:#9aa2b1}}
    text{font-family:ui-sans-serif,-apple-system,'Segoe UI',Roboto,sans-serif}
    </style>""",
        f'<rect class="surface" width="{width}" height="{height}"/>',
        '<text class="ink" x="16" y="26" font-size="13" font-weight="600">Estimation des flux de report par le modèle</text>',
        f'<text class="muted" x="16" y="44" font-size="11">Flux médians de la distribution prédictive a priori sur {district_count} duels {targets[0]}/{targets[1]}. La largeur des flux correspond au nombre de voix.</text>',
        f'<text class="muted" x="16" y="{top - 12}" font-size="10" letter-spacing="0.06em">RESERVOIR</text>',
        f'<text class="muted" x="{right_x + node_width}" y="{top - 12}" font-size="10" letter-spacing="0.06em" text-anchor="end">SECOND ROUND</text>',
    ]

    left_cursor = {name: left[name][0] for name in sources}
    right_cursor = {name: right[name][0] for name in targets}
    ribbons = []
    for source in sources:
        for target_index, target in enumerate(targets):
            value = flows[source][target_index][0]
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
    for _, source, left_y, right_y, ribbon_height in sorted(
        ribbons, key=lambda ribbon: ribbon[0], reverse=True
    ):
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
            if previous is not None and centre - previous < 26:
                centre = previous + 26
            labels[name], previous = centre, centre
        return labels

    for names, x, anchor, positions, totals in (
        (sources, left_x, "end", left, source_totals),
        (targets, right_x, "start", right, target_totals),
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
            parts.extend(
                [
                    f'<text class="ink" x="{text_x}" y="{label_y - 1:.1f}" font-size="11.5" font-weight="600" text-anchor="{anchor}">{escape(name)}</text>',
                    f'<text class="muted" x="{text_x}" y="{label_y + 11:.1f}" font-size="10" text-anchor="{anchor}">{totals[name] / 1000:,.0f}k</text>',
                ]
            )

    largest_party = max(
        (source for source in sources if source != "NON_EXPRIMES"),
        key=source_totals.get,
    )
    notes = [
        (largest_party, 0, f"{largest_party} → {targets[0]}"),
        (largest_party, 1, f"{largest_party} → {targets[1]}"),
        ("NON_EXPRIMES", 2, "non-voters staying home"),
    ]
    intervals = "  ·  ".join(
        f"{label} {flows[source][index][1] / 1000:,.0f}k–{flows[source][index][2] / 1000:,.0f}k"
        for source, index, label in notes
    )
    parts.extend(
        [
            f'<text class="muted" x="16" y="{height - bottom + 8}" font-size="10.5">90% prior interval — {escape(intervals)}</text>',
            f'<text class="muted" x="16" y="{height - bottom + 23}" font-size="10.5">The bands are enormous: the model has an ORDER, not a rate. Nothing here is fitted to the second round.</text>',
        ]
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Prior-predictive vote flows in {district_count} runoffs.">'
        f'{"".join(parts)}</svg>\n'
    )
