"""Comment le noyau mélange une composante nationale et une composante locale.

Une ligne de report a autant de cellules que de destinations ; chacune tire son
propre `z_national` (partagé) et son propre `z_local,c` (un par circonscription,
corrélé par le noyau département/région). Cette illustration fixe TOUT le reste
du modèle (alpha, corrélations, la valeur de lambda) pour isoler ce seul
mécanisme : national seul (lambda=1), local seul par circonscription (lambda=0),
puis le mélange effectivement utilisé (lambda=0,5).

Les tirages sont RÉELS — produits par `KernelModel._local_latent_field` et par
`ordinal.uniforms_to_gammas`/`gammas_to_row`, le même code que la simulation —,
à une seed fixée pour la reproductibilité de la figure, pas des valeurs choisies
à la main."""

from xml.sax.saxutils import escape

import numpy as np
from scipy.stats import norm as _norm_dist

from analyse_legislatives.circonscription import Circonscription, CirconscriptionResult
from analyse_legislatives.models import build
from analyse_legislatives.models.ordinal import gammas_to_row, uniforms_to_gammas
from analyse_legislatives.parties import (
    DESTINATIONS,
    NON_EXPRIMES,
    PoliticalFamily,
    label,
)
from analyse_legislatives.publication.illustrations._shared import (
    party_colour,
    readable_ink,
    theme_style,
)

SEED = 1
ALPHA = 1.0
DEPARTMENT_RHO = 0.7
REGION_RHO = 0.3
MIXING_LAMBDA = 0.5

SOURCE = PoliticalFamily.NFPx
# Ordre RESTREINT et strict (aucun ex æquo) : `NFP+` déclare `{DVG} > {ENS+} > ...`,
# donc un duel DVG/ENS+ donne directement DVG ≻ ENS+ ≻ NON_EXPRIMES sans qu'aucune
# paire ne soit à départager — la figure isole le mélange, pas le tie-break, qui a
# sa propre illustration (`preference-orderings.svg`).
DESTINATIONS_ORDER = (PoliticalFamily.DVG, PoliticalFamily.ENSx, NON_EXPRIMES)

DISTRICTS = ("0101", "0102", "7501")
DISTRICT_NOTE = {
    "0101": "Ain (01)",
    "0102": "Ain (01)",
    "7501": "Paris (75)",
}

BAR_W, BAR_H = 470, 30
# Aucune couleur dédiée par étape : les trois sections sont des moments d'UNE
# même quantité, pas trois catégories différentes — leur assigner une teinte
# chacune suggérerait le contraire. Seule la couleur des partis, dans les
# barres, porte une vraie information ; le reste de la figure reste en encre,
# gris et un unique accent repris du site (voir `theme_style`).


def _bare_district(district_id: str) -> CirconscriptionResult:
    """Un porteur d'identifiant seul : `_local_latent_field` ne lit que
    `circonscription.id`, aucune donnée électorale n'est nécessaire ici."""
    empty = dict.fromkeys(DESTINATIONS, 0)
    return CirconscriptionResult(
        Circonscription(district_id, district_id), dict(empty), dict(empty), 0
    )


def _rows() -> tuple[dict, dict, dict]:
    """Calcule les trois rangées (national, local, mélange) avec le code réel du
    modèle : `_local_latent_field` pour le champ local corrélé, puis le même
    passage Gamma / tri / normalisation que la simulation."""
    model = build(
        "kernel_anchored",
        seed=SEED,
        department_correlation=DEPARTMENT_RHO,
        region_correlation=REGION_RHO,
        dirichlet_concentration=ALPHA,
    )
    districts = [_bare_district(d) for d in DISTRICTS]

    z_nat = model.rng.standard_normal(len(DESTINATIONS_ORDER))
    z_loc = {
        destination: model._local_latent_field(districts)
        for destination in DESTINATIONS_ORDER
    }

    def row_at(weight: float) -> dict:
        mixed = {
            destination: np.sqrt(weight) * z_nat[i]
            + np.sqrt(1 - weight) * z_loc[destination]
            for i, destination in enumerate(DESTINATIONS_ORDER)
        }
        uniforms = {d: _norm_dist.cdf(v) for d, v in mixed.items()}
        gammas = uniforms_to_gammas(uniforms, ALPHA)
        return gammas_to_row(gammas, list(DESTINATIONS_ORDER), ())

    national = row_at(1.0)  # lambda=1 : le terme local s'annule, une seule valeur
    local = row_at(0.0)  # lambda=0 : le terme national s'annule
    mixed = row_at(MIXING_LAMBDA)
    return national, local, mixed


def _segmented_bar(x: int, y: int, shares: dict, width: int = BAR_W) -> str:
    """Segments accolés, sans liseré blanc : sur fond sombre un liseré blanc
    devient une ligne translucide incongrue plutôt qu'un espacement propre. La
    séparation entre segments vient d'un trait fin `.rule`, cohérent dans les
    deux thèmes ; seul le contour extérieur du bloc est tracé."""
    parts = []
    cursor = float(x)
    for destination in DESTINATIONS_ORDER:
        share = float(shares[destination])
        segment_w = share * width
        fill = party_colour(destination)
        parts.append(
            f'<rect x="{cursor:.1f}" y="{y}" width="{max(segment_w, 0.5):.1f}" '
            f'height="{BAR_H}" fill="{fill}"/>'
        )
        if segment_w > 34:
            text_colour = readable_ink(fill)
            parts.append(
                f'<text x="{cursor + segment_w / 2:.1f}" y="{y + BAR_H / 2 + 4}" '
                f'text-anchor="middle" font-size="11" font-weight="650" '
                f'fill="{text_colour}">{share * 100:.0f}&#8201;%</text>'
            )
        cursor += segment_w
        if cursor < x + width - 1:
            parts.append(
                f'<line x1="{cursor:.1f}" y1="{y}" x2="{cursor:.1f}" y2="{y + BAR_H}" '
                f'class="rule" stroke-width="1"/>'
            )
    parts.append(
        f'<rect x="{x}" y="{y}" width="{width}" height="{BAR_H}" rx="3" '
        f'fill="none" class="rule" stroke-width="1"/>'
    )
    return "".join(parts)


def _legend(x: int, y: int) -> str:
    parts = []
    cursor = x
    for destination in DESTINATIONS_ORDER:
        fill = party_colour(destination)
        text = label(destination) if destination != NON_EXPRIMES else "Non exprimés"
        parts.append(
            f'<rect x="{cursor}" y="{y - 9}" width="10" height="10" rx="2" fill="{fill}"/>'
        )
        parts.append(
            f'<text class="muted" x="{cursor + 15}" y="{y}" font-size="10.5">{escape(text)}</text>'
        )
        cursor += 15 + len(text) * 6.1 + 20
    return "".join(parts)


def _section_header(x: int, y: int, width: int, number: str, text: str) -> list[str]:
    """Un filet fin au-dessus d'une légende en phrase — pas un bandeau coloré :
    la numérotation (seule touche d'accent) suffit à marquer l'étape."""
    return [
        f'<line x1="{x}" y1="{y}" x2="{x + width}" y2="{y}" class="rule" stroke-width="1"/>',
        f'<text x="{x}" y="{y + 22}" font-size="12.5">'
        f'<tspan class="accent" font-weight="700">{number}</tspan> '
        f'<tspan class="ink" font-weight="600">{escape(text)}</tspan></text>',
    ]


def build_national_local_mixing_svg() -> str:
    national, local, mixed = _rows()

    width = 900
    content_w = width - 48
    bar_x = 250
    row_gap = 46
    zone_pad_top = 45  # du haut d'une zone jusqu'au centre de sa première barre

    parts = [
        theme_style(),
        '<text class="ink" x="24" y="29" font-size="16.5" font-weight="650">'
        "Mélanger une ligne nationale et des lignes locales</text>",
        '<text class="muted" x="24" y="49" font-size="11.3">'
        "Réservoir NFP+, duel DVG/ENS+ — un exemple, à λ=0,5. "
        "Même tirage réel, montré à trois pondérations.</text>",
    ]

    # ------------------------------------------------------------ 1. national
    zone1_y, zone1_h = 74, 76
    parts.extend(
        _section_header(
            24,
            zone1_y,
            content_w,
            "1.",
            "Tirage national (λ=1) — une valeur par cellule, partagée par toute la France",
        )
    )
    parts.extend(
        [
            _segmented_bar(
                bar_x,
                zone1_y + zone_pad_top,
                {d: national[d][0] for d in DESTINATIONS_ORDER},
            ),
            f'<text class="muted" x="{bar_x - 14}" y="{zone1_y + zone_pad_top + BAR_H / 2 + 4:.0f}" '
            f'text-anchor="end" font-size="11" font-weight="600">France</text>',
        ]
    )

    # -------------------------------------------------------------- 2. local
    zone2_y = zone1_y + zone1_h + 24
    zone2_h = zone_pad_top + 3 * row_gap - (row_gap - BAR_H) + 12
    parts.extend(
        _section_header(
            24,
            zone2_y,
            content_w,
            "2.",
            "Tirages locaux (λ=0) — un par circonscription, corrélés par le noyau",
        )
    )
    local_y0 = zone2_y + zone_pad_top
    for i, district_id in enumerate(DISTRICTS):
        y = local_y0 + i * row_gap
        shares = {d: local[d][i] for d in DESTINATIONS_ORDER}
        parts.append(_segmented_bar(bar_x, y, shares))
        parts.append(
            f'<text class="ink" x="{bar_x - 14}" y="{y + BAR_H / 2 + 4}" text-anchor="end" '
            f'font-size="11.5" font-weight="650">{district_id}</text>'
        )
        parts.append(
            f'<text class="muted" x="{bar_x - 14}" y="{y + BAR_H / 2 + 17}" text-anchor="end" '
            f'font-size="9">{DISTRICT_NOTE[district_id]}</text>'
        )
    bracket_top = local_y0 + BAR_H / 2
    bracket_bottom = local_y0 + row_gap + BAR_H / 2
    bracket_x = bar_x + BAR_W + 16
    half = (bracket_bottom - bracket_top) / 2
    parts.extend(
        [
            f'<path d="M{bracket_x} {bracket_top:.1f} q10 0 10 {half:.1f} '
            f'q0 {half:.1f} -10 {half * 2:.1f}" fill="none" class="rule" stroke-width="1.4"/>',
            f'<text class="muted" x="{bracket_x + 16}" y="{(bracket_top + bracket_bottom) / 2 + 4:.0f}" '
            f'font-size="9.5">même département<tspan x="{bracket_x + 16}" dy="12">'
            f"(&#961;=0,7 entre elles)</tspan></text>",
        ]
    )
    y_last = local_y0 + 2 * row_gap
    parts.append(
        f'<text class="muted" x="{bracket_x + 16}" y="{y_last + BAR_H / 2 + 4:.0f}" '
        f'font-size="9.5">autre région : indépendante<tspan x="{bracket_x + 16}" dy="12">'
        f"de 0101 et 0102 ici</tspan></text>"
    )

    # ---------------------------------------------------------------- fusion
    fuse_y = zone2_y + zone2_h + 22
    parts.append(
        f'<text class="muted" x="{width / 2}" y="{fuse_y}" text-anchor="middle" '
        'font-size="10.5">chaque circonscription mélange &#8730;λ &#215; (valeur '
        "nationale) + &#8730;(1−λ) &#215; (sa valeur locale), ici avec λ=0,5</text>"
    )

    # ------------------------------------------------------------- 3. mixed
    zone3_y = fuse_y + 20
    zone3_h = zone2_h
    parts.extend(
        _section_header(
            24,
            zone3_y,
            content_w,
            "3.",
            "Ligne mélangée (λ=0,5) — ce que la simulation utilise réellement",
        )
    )
    mixed_y0 = zone3_y + zone_pad_top
    for i, district_id in enumerate(DISTRICTS):
        y = mixed_y0 + i * row_gap
        shares = {d: mixed[d][i] for d in DESTINATIONS_ORDER}
        parts.append(_segmented_bar(bar_x, y, shares))
        parts.append(
            f'<text class="ink" x="{bar_x - 14}" y="{y + BAR_H / 2 + 4}" text-anchor="end" '
            f'font-size="11.5" font-weight="650">{district_id}</text>'
        )

    legend_y = zone3_y + zone3_h + 24
    caption_y = legend_y + 22
    parts.append(_legend(bar_x, legend_y))
    parts.append(
        f'<text class="muted" x="24" y="{caption_y}" font-size="10">'
        "0101 et 0102 restent plus proches l’une de l’autre qu’elles ne le sont "
        "de 7501, même après mélange — l’effet du noyau s’atténue avec "
        "λ sans disparaître.</text>"
    )

    height = caption_y + 16
    parts.insert(1, f'<rect class="surface" width="{width}" height="{height}"/>')

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Mélange d’une ligne de report nationale et de '
        'lignes locales corrélées par le noyau, à lambda=0,5">'
        f'{"".join(parts)}</svg>\n'
    )
