"""Animated walkthrough of one complete district simulation."""

import json
from collections.abc import Iterable, Mapping
from typing import Any
from xml.sax.saxutils import escape

from analyse_legislatives.config import PROJECT_ROOT
from analyse_legislatives.parties import SPECTRUM_ORDER, label as party_label
from analyse_legislatives.publication.illustrations._shared import ABS_COLOR
from analyse_legislatives.viz.palette import POLITICAL_FAMILY_COLORS

ANIMATION_STEP_SECONDS = 2.4
ANIMATION_STEPS = 5
EXAMPLE_ARTIFACT = PROJECT_ROOT / "artifacts/publication/examples/district-0101.json"


def _load_example() -> dict:
    if not EXAMPLE_ARTIFACT.exists():
        raise FileNotFoundError(
            f"Missing {EXAMPLE_ARTIFACT}. Run "
            "`python scripts/analyses/simulation_example.py` first."
        )
    return json.loads(EXAMPLE_ARTIFACT.read_text(encoding="utf-8"))


def _pairs(rows: Iterable[Mapping[str, Any]]) -> list[tuple[str, int | float]]:
    return [(row["party"], row["value"]) for row in rows]


def build_simulation_animation_svg() -> str:
    example = _load_example()
    first_round = example["first_round"]
    draw = example["example_draw"]
    predictive = example["predictive"]
    r1 = _pairs(first_round["competing"])
    reservoirs = _pairs(first_round["reservoirs"])
    theta_row = _pairs(draw["theta_row"])
    restricted = _pairs(draw["restricted_row"])
    multinomial = _pairs(draw["multinomial"])
    totals = _pairs(draw["totals"])
    actual = _pairs(example["actual"]["votes"])
    main_reservoirs = sorted(reservoirs, key=lambda item: item[1], reverse=True)[:3]
    label_width = 84
    column_width, column_gap = 266, 26
    left, top, body_height = 18, 104, 168
    width = left * 2 + column_width * 3 + column_gap * 2
    height = top + body_height * 2 + 96
    cycle = ANIMATION_STEPS * ANIMATION_STEP_SECONDS
    slot = 100 / ANIMATION_STEPS
    by_label = {party_label(party): party for party in SPECTRUM_ORDER}

    def colour(name: str) -> str:
        if name == "NON_EXPRIMES":
            return ABS_COLOR
        return POLITICAL_FAMILY_COLORS[by_label[name]]

    keyframes = []
    for index in range(ANIMATION_STEPS):
        start, end = index * slot, (index + 1) * slot
        keyframes.append(
            f"@keyframes on{index}{{0%,{max(0, start - 0.01):.2f}%{{opacity:.26}}"
            f"{start:.2f}%,{end:.2f}%{{opacity:1}}"
            f"{min(100, end + 0.01):.2f}%,100%{{opacity:.26}}}}"
        )
    animation = "".join(
        f".on{index}{{animation:on{index} {cycle}s steps(1,end) infinite}}"
        for index in range(ANIMATION_STEPS)
    )
    parts = [
        f"""<style>
    .surface{{fill:#fbfbfc}}.ink{{fill:#16181d}}.muted{{fill:#5a616e}}
    .hair{{stroke:#d9dce2}}.faint{{stroke:#e8eaee}}
    @media(prefers-color-scheme:dark){{.surface{{fill:#14161a}}.ink{{fill:#e9eaee}}
    .muted{{fill:#9aa2b1}}.hair{{stroke:#3a4049}}.faint{{stroke:#23262c}}}}
    text{{font-family:ui-sans-serif,-apple-system,'Segoe UI',Roboto,sans-serif}}
    {''.join(keyframes)}{animation}
    @media(prefers-reduced-motion:reduce){{.on0,.on1,.on2,.on3,.on4{{animation:none;opacity:1}}}}
    </style>""",
        f'<rect class="surface" width="{width}" height="{height}"/>',
        f'<text class="ink" x="{left}" y="32" font-size="15" font-weight="600">Circonscription {escape(example["district"]["id"])} — {escape(example["district"]["name"])}</text>',
        f'<text class="muted" x="{left}" y="54" font-size="11.5">{r1[0][0]} finished the first round ahead, {r1[0][1]:,} to {r1[1][1]:,}. Main reservoirs: {main_reservoirs[0][1]:,} {main_reservoirs[0][0]}, {main_reservoirs[1][1]:,} {main_reservoirs[1][0]}, {main_reservoirs[2][1]:,} {main_reservoirs[2][0]}.</text>',
        f'<text class="muted" x="{left}" y="72" font-size="11.5">Values are loaded from the election files and a reproducible {escape(example["model"])} draw.</text>',
    ]
    steps = [
        ("Draw a matrix", "one Θ for the whole country"),
        ("Keep what is on the ballot", "five of eight columns go"),
        ("Split each reservoir", "a multinomial draw"),
        ("Count", "the seat goes to whoever leads"),
        ("Do it again", "and again, and again"),
    ]

    def position(index: int) -> tuple[int, int]:
        column, row = index % 3, index // 3
        return (
            left + column * (column_width + column_gap),
            top + row * (body_height + 34),
        )

    for index, (title, subtitle) in enumerate(steps):
        x, y = position(index)
        parts.extend(
            [
                f'<g class="on{index}">',
                f'<line class="hair" x1="{x}" y1="{y - 16}" x2="{x + column_width}" y2="{y - 16}"/>',
                f'<text class="muted" x="{x}" y="{y}" font-size="10.5">{index + 1}</text>',
                f'<text class="ink" x="{x + 16}" y="{y}" font-size="12" font-weight="600">{escape(title)}</text>',
                f'<text class="muted" x="{x + 16}" y="{y + 15}" font-size="10">{escape(subtitle)}</text>',
            ]
        )
        chart_x, chart_y, bar_width = x + 16, y + 34, 104
        if index in (0, 1):
            retained = {name for name, _ in restricted}
            for row, (name, value) in enumerate(theta_row):
                row_y = chart_y + row * 13
                visible = index == 0 or name in retained
                opacity = 1 if visible else 0.22
                fill = colour(name) if visible else "#aeb4bd"
                parts.append(
                    f'<text class="muted" x="{chart_x}" y="{row_y + 7}" font-size="8.5" opacity="{opacity}">{name}</text>'
                    f'<rect x="{chart_x + label_width}" y="{row_y}" width="{max(1.5, value * bar_width):.1f}" height="8" fill="{fill}" opacity="{opacity}"/>'
                    f'<text class="muted" x="{chart_x + label_width + 4 + max(1.5, value * bar_width):.0f}" y="{row_y + 7}" font-size="8.5" opacity="{opacity}">{value:.3f}</text>'
                )
            if index == 1:
                for row, (name, value) in enumerate(restricted):
                    parts.append(
                        f'<text class="ink" x="{chart_x}" y="{chart_y + 104 + row * 14}" font-size="10" font-weight="600">{name}</text>'
                        f'<text class="ink" x="{chart_x + label_width + 10}" y="{chart_y + 104 + row * 14}" font-size="10">{value:.2f}</text>'
                    )
                parts.append(
                    f'<text class="muted" x="{chart_x + label_width + 46}" y="{chart_y + 104}" font-size="9">renormalised</text>'
                )
        elif index == 2:
            source_pool = dict(reservoirs)[draw["source"]]
            max_transfer = max(value for _, value in multinomial)
            parts.append(
                f'<text class="muted" x="{chart_x}" y="{chart_y}" font-size="9">the {draw["source"]} reservoir, {source_pool:,} voters</text>'
            )
            for row, (name, value) in enumerate(multinomial):
                row_y = chart_y + 16 + row * 24
                width_value = value / max_transfer * 92
                parts.append(
                    f'<text class="muted" x="{chart_x}" y="{row_y + 12}" font-size="9.5">{name}</text>'
                    f'<rect x="{chart_x + label_width}" y="{row_y}" width="{max(2, width_value):.0f}" height="15" fill="{colour(name)}"/>'
                    f'<text class="ink" x="{chart_x + label_width + 6 + width_value:.0f}" y="{row_y + 12}" font-size="10">{value:,}</text>'
                )
            parts.append(
                f'<text class="muted" x="{chart_x}" y="{chart_y + 104}" font-size="9.5">the other reservoirs split the same way</text>'
            )
        elif index == 3:
            max_total = max(value for _, value in totals)
            for row, (name, value) in enumerate(totals):
                row_y = chart_y + 12 + row * 40
                width_value = value / max_total * 132
                parts.append(
                    f'<rect x="{chart_x}" y="{row_y}" width="{width_value:.0f}" height="19" fill="{colour(name)}"/>'
                    f'<text class="ink" x="{chart_x}" y="{row_y - 4}" font-size="10" font-weight="600">{name}</text>'
                    f'<text class="ink" x="{chart_x + width_value + 6:.0f}" y="{row_y + 14}" font-size="10.5">{value:,}</text>'
                )
            parts.append(
                f'<text class="muted" x="{chart_x}" y="{chart_y + 100}" font-size="9.5">in this draw the seat goes to {draw["winner"]}</text>'
            )
        else:
            histogram = predictive["histogram_counts"]
            histogram_scale = max(histogram)
            for bar, count in enumerate(histogram):
                bar_height = count / histogram_scale * 55
                parts.append(
                    f'<rect x="{chart_x + bar * 13}" y="{chart_y + 58 - bar_height:.1f}" width="11" height="{bar_height:.1f}" fill="{colour(predictive["focus_party"])}" opacity="0.62"/>'
                )
            parts.append(
                f'<line class="faint" x1="{chart_x}" y1="{chart_y + 58}" x2="{chart_x + 182}" y2="{chart_y + 58}"/>'
                f'<line class="hair" x1="{chart_x + 24}" y1="{chart_y + 6}" x2="{chart_x + 24}" y2="{chart_y + 58}" stroke-width="1.5"/>'
                f'<text class="ink" x="{chart_x + 20}" y="{chart_y - 2}" font-size="9" font-weight="700">what happened</text>'
                f'<text class="ink" x="{chart_x}" y="{chart_y + 82}" font-size="10.5" font-weight="600">{predictive["focus_party"]} wins {predictive["win_probability"]:.0%} of {example["n_simulations"]:,} draws</text>'
                f'<text class="muted" x="{chart_x}" y="{chart_y + 96}" font-size="9.5">{example["actual"]["winner"]} took it, {actual[0][1]:,} to {actual[1][1]:,}</text>'
            )
        parts.append("</g>")

    parts.append(
        f'<line class="faint" x1="{left}" y1="{height - 42}" x2="{width - left}" y2="{height - 42}"/>'
        f'<text class="muted" x="{left}" y="{height - 22}" font-size="10.5">Steps 1 and 2 happen once per simulation; 3 and 4 run in all {example["national_district_count"]} districts. Repeated draws favour {predictive["focus_party"]}, but {example["actual"]["winner"]} won —</text>'
        f'<text class="muted" x="{left}" y="{height - 8}" font-size="10.5">the same over-projection of the far right that the results section takes apart.</text>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Five steps of one simulation in district {escape(example["district"]["id"])}.">'
        f'{"".join(parts)}</svg>\n'
    )
