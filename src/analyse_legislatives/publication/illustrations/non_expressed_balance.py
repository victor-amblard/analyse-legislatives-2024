"""Un tirage du modèle SANS ancrage, et le solde qu'il implique — circo 5908.

Même structure que `turnout_flows`, mais sur un cas réel et sans la boîte
« partis qualifiés » du second tour : ce qui s'explique ici, c'est le RÉSERVOIR
des non-exprimés, pas la répartition entre finalistes.

Sens de lecture : les taux portés par les flèches sont TIRÉS (un tirage réel de
`models.build("national")`, à graine fixée, pas des nombres ronds inventés) ;
le réservoir du second tour et son solde en sont DÉDUITS par comptabilité. La
figure ne montre donc pas des flux observés — ils ne le sont jamais, c'est
l'inférence écologique — mais ce qu'implique un jeu de taux plausible.

Tout est recalculé à l'exécution : rien n'est recopié à la main, donc rien ne
peut diverger du modèle. Les réservoirs suivent la partition du modèle
lui-même : les éliminés d'une famille encore qualifiée passent par la ligne de
cette famille (gouvernée par la démobilisation), pas par une ligne de report.

STRICTEMENT A PRIORI : le second tour n'est pas chargé ici, et cette figure ne
doit rien en dire. Elle paraît dans le billet avant toute évaluation, où
afficher le résultat réel reviendrait à s'en servir pour justifier le modèle
qui le précède. C'est aussi pourquoi `load_second_round_results` n'est pas
importé : la fuite est rendue impossible, pas seulement évitée.

5908 (Nord) sert d'exemple parce que le réservoir y est énorme — 47,9 % des
inscrits — donc que le sort qu'on lui réserve y pèse le plus lourd.
"""

from analyse_legislatives.data import load_full_results
from analyse_legislatives.models import build
from analyse_legislatives.parties import NON_EXPRIMES
from analyse_legislatives.publication.illustrations._shared import theme_style
from analyse_legislatives.transfers import normalize_for_district

DISTRICT_ID = "5908"
DISTRICT_LABEL = "Circonscription 5908 (Nord) : duel NFP+ / RN+"
SEED = 20240755
"""Graine retenue pour que les DEUX tirages soient proches de leur médiane, et
non pour flatter le modèle : à la graine par défaut, l'ancrage tombait à deux
écarts-types de la sienne et exigeait une mobilisation spectaculaire, ce qui
aurait fait passer un cas de queue pour le régime ordinaire."""


def _fr(n: int, *, sign: bool = False) -> str:
    """Sépare les milliers par une espace, à la française."""
    return (f"{n:+,}" if sign else f"{n:,}").replace(",", " ")


def _pct(x: float) -> str:
    return f"{x * 100:.1f} %".replace(".", ",")


def _draw_balance() -> dict:
    """Un tirage, puis la comptabilité du réservoir qui en découle."""
    first_round = load_full_results()
    district = next(
        d for d in first_round.districts if d.circonscription.id == DISTRICT_ID
    )

    model = build("national", seed=SEED)
    draw = model.draw_simulation()
    matrix = model.sample_transfer_matrices([district], draw)[0]
    rows = normalize_for_district(matrix, district, draw.tilt)

    qualified = district.competing_parties_results
    eliminated = district.eliminated_parties_results
    # Partition DU MODÈLE : un éliminé dont la famille reste qualifiée emprunte
    # la ligne de cette famille, donc la démobilisation, et non un report.
    governed = sum(qualified.values()) + sum(
        v for p, v in eliminated.items() if qualified.get(p, 0) > 0
    )
    others = {p: v for p, v in eliminated.items() if qualified.get(p, 0) == 0 and v > 0}
    registered = first_round.inscrits_by_id[DISTRICT_ID]
    reservoir = registered - governed - sum(others.values())

    retention = draw.non_expressed_retention
    demobilisation = draw.qualified_demobilisation
    stays = round(retention * reservoir)
    reports = {
        p: (rows.rates[p][NON_EXPRIMES], round(rows.rates[p][NON_EXPRIMES] * v))
        for p, v in others.items()
    }
    predicted = (
        stays
        + round(demobilisation * governed)
        + sum(count for _, count in reports.values())
    )

    return {
        "registered": registered,
        "qualified": {str(p): v for p, v in qualified.items() if v > 0},
        "governed": governed,
        "others": {str(p): v for p, v in others.items()},
        "reservoir": reservoir,
        "retention": retention,
        "stays": stays,
        "mobilised": reservoir - stays,
        "demobilisation": demobilisation,
        "demobilised": round(demobilisation * governed),
        "reports": {str(p): v for p, v in reports.items()},
        "predicted": predicted,
    }


def _solve_balance() -> dict:
    """Le pendant ancré : on VISE une part de suffrages exprimés, et la
    rétention des non-exprimés en est déduite par comptabilité.

    `delta_nat` dépend de la moyenne nationale et `delta_c` du champ local :
    impossible de les obtenir sur une seule circonscription, d'où le tirage sur
    les 501. On relit ensuite la matrice de la seule 5908 — c'est le modèle qui
    résout, pas cette fonction, donc la figure ne peut pas raconter autre chose
    que ce que fait le code.
    """
    first_round = load_full_results()
    districts = first_round.districts
    index = [d.circonscription.id for d in districts].index(DISTRICT_ID)
    district = districts[index]

    model = build("kernel_anchored", seed=SEED)
    draw = model.draw_simulation()
    matrices = model.sample_transfer_matrices(districts, draw)
    matrix = matrices[index]
    rows = normalize_for_district(matrix, district, draw.tilt)

    qualified = district.competing_parties_results
    eliminated = district.eliminated_parties_results
    governed = sum(qualified.values()) + sum(
        v for p, v in eliminated.items() if qualified.get(p, 0) > 0
    )
    others = {p: v for p, v in eliminated.items() if qualified.get(p, 0) == 0 and v > 0}
    registered = first_round.inscrits_by_id[DISTRICT_ID]
    reservoir = registered - governed - sum(others.values())

    retention = matrix.rates[NON_EXPRIMES][NON_EXPRIMES]
    demobilisation = 1.0 - next(iter(matrix.own_retentions.values()))
    stays = round(retention * reservoir)
    reports = {
        p: (rows.rates[p][NON_EXPRIMES], round(rows.rates[p][NON_EXPRIMES] * v))
        for p, v in others.items()
    }
    targeted = (
        stays
        + round(demobilisation * governed)
        + sum(count for _, count in reports.values())
    )

    return {
        "registered": registered,
        "qualified": {str(p): v for p, v in qualified.items() if v > 0},
        "governed": governed,
        "others": {str(p): v for p, v in others.items()},
        "reservoir": reservoir,
        "retention": retention,
        "stays": stays,
        "mobilised": reservoir - stays,
        "demobilisation": demobilisation,
        "demobilised": round(demobilisation * governed),
        "reports": {str(p): v for p, v in reports.items()},
        "predicted": targeted,
    }


def _box(
    x: int,
    y: int,
    w: int,
    h: int,
    title: str,
    lines: tuple[str, ...],
    highlight: bool = False,
) -> str:
    body = "".join(
        f'<text class="muted" x="{x + w / 2}" y="{y + 39 + i * 14}" '
        f'text-anchor="middle" font-size="9.6">{line}</text>'
        for i, line in enumerate(lines)
    )
    border = (
        'class="accent-line" fill="none" stroke-width="2"'
        if highlight
        else 'class="frame" stroke-width="1"'
    )
    return (
        f'<rect {border} x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>'
        f'<text class="{"accent" if highlight else "ink"}" x="{x + w / 2}" '
        f'y="{y + 22}" text-anchor="middle" font-size="11.5" '
        f'font-weight="650">{title}</text>{body}'
    )


def _flow(
    path: str,
    cx: float,
    cy: float,
    label: str,
    votes: str,
    dashed: bool = False,
    highlight: bool = False,
    width_hint: float | None = None,
) -> str:
    """Flèche + étiquette sur deux lignes : le taux, puis les voix qu'il déplace.

    `highlight` encadre l'étiquette et passe le trait à l'accent : c'est le taux
    que l'ON FIXE, par opposition à tout ce que la figure en déduit. La figure
    jumelle du modèle ancré se construit en déplaçant ce seul drapeau — là, le
    taux encadré devient le réservoir visé, et `t_NE,NE` en est déduit.

    `width_hint` sert quand `label` contient du balisage (indices en `tspan`) :
    la longueur de la chaîne ne dit alors plus rien de sa largeur rendue.
    """
    dash = ' stroke-dasharray="4 3"' if dashed else ""
    half = width_hint or 3.35 * max(len(label), len(votes)) + 9
    stroke = "accent-line" if highlight else "rule"
    frame = (
        f'<rect x="{cx - half}" y="{cy - 14}" width="{2 * half}" height="33" '
        f'rx="5" class="accent-line" fill="none" stroke-width="1.2"/>'
        if highlight
        else ""
    )
    return (
        f'<path d="{path}" fill="none" class="{stroke}" '
        f'stroke-width="{2 if highlight else 1.5}"{dash} '
        f'marker-end="url(#flow-arrow)"/>'
        f'<rect class="surface" x="{cx - half}" y="{cy - 14}" width="{2 * half}" '
        f'height="33" rx="5" opacity="0.96"/>{frame}'
        f'<text class="{"accent" if highlight else "ink"}" x="{cx}" y="{cy}" '
        f'text-anchor="middle" font-size="10"'
        f"{' font-weight="650"' if highlight else ''}>{label}</text>"
        f'<text class="muted" x="{cx}" y="{cy + 13}" text-anchor="middle" '
        f'font-size="9.4">{votes}</text>'
    )


def _render(d: dict, *, anchored: bool) -> str:
    """Les deux figures, au drapeau près.

    `anchored=False` : on fixe `t_NE,NE`, le réservoir du second tour en découle.
    `anchored=True`  : on vise le réservoir, `t_NE,NE` en est déduit.
    Même mise en page, même comptabilité — seul change ce qui est encadré, pour
    que la comparaison des deux figures ne porte que sur le SENS de la déduction.
    """
    # 430 et non 400 : la flèche de mobilisation descend jusqu'à y = 368 et son
    # étiquette jusqu'à 371 ; la légende du bas doit passer SOUS elle.
    width, height = 780, 430
    box_w, right_x, right_w = 200, 566, 188
    net = d["predicted"] - d["reservoir"]
    centre = right_x + right_w / 2

    report_party, (report_rate, report_votes) = next(iter(d["reports"].items()))

    parts = [
        theme_style(),
        """<defs>
        <marker id="flow-arrow" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0L10 5L0 10Z" class="muted"/></marker>
        </defs>""",
        f'<rect class="surface" width="{width}" height="{height}"/>',
        '<text class="ink" x="24" y="29" font-size="16" font-weight="650">'
        + (
            "On vise une participation, et les flux s’ajustent"
            if anchored
            else "Des taux ordinaires, et le réservoir se vide"
        )
        + "</text>",
        f'<text class="muted" x="24" y="49" font-size="11">{DISTRICT_LABEL} · '
        f"{_fr(d['registered'])} inscrits · un tirage du modèle "
        + ("ancré" if anchored else "national")
        + "</text>",
        '<text class="muted" x="124" y="76" text-anchor="middle" font-size="10.5" '
        'font-weight="650">Premier tour</text>',
        f'<text class="muted" x="{centre}" y="76" text-anchor="middle" '
        'font-size="10.5" font-weight="650">Second tour</text>',
        _box(
            24,
            88,
            box_w,
            66,
            "Partis qualifiés",
            (
                "  ·  ".join(f"{p} {_fr(v)}" for p, v in d["qualified"].items()),
                f"{_fr(d['governed'])} voix (avec leurs éliminés)",
            ),
        ),
        _box(
            24,
            176,
            box_w,
            66,
            "Parti éliminé",
            (report_party, f"{_fr(d['others'][report_party])} voix"),
        ),
        _box(
            24,
            264,
            box_w,
            66,
            "Non exprimés",
            (
                f"{_fr(d['reservoir'])} voix",
                f"{d['reservoir'] / d['registered'] * 100:.1f} % des inscrits".replace(
                    ".", ","
                ),
            ),
        ),
        _box(
            right_x,
            172,
            right_w,
            76,
            "Non exprimés",
            (
                f"{_fr(d['predicted'])} voix",
                f"{d['predicted'] / d['registered'] * 100:.1f} % des inscrits".replace(
                    ".", ","
                ),
            ),
            highlight=anchored,
        ),
    ]

    parts.extend(
        [
            _flow(
                "M228 122 C350 122 440 164 562 194",
                366,
                136,
                f"démobilisation  {_pct(d['demobilisation'])}",
                f"{_fr(d['demobilised'])} voix",
            ),
            _flow(
                "M228 209 C340 209 450 209 562 210",
                372,
                199,
                f"reports vers les non-exprimés  {_pct(report_rate)}",
                f"{_fr(report_votes)} voix",
            ),
            # Le pivot des deux figures : encadré quand on le FIXE (modèle
            # national), simple étiquette quand il est DÉDUIT (modèle ancré).
            _flow(
                "M228 296 C350 296 440 256 562 232",
                352,
                278,
                # Écart posé par `dx`, pas par une espace : SVG replie les
                # espaces en tête de `tspan` (l'espace insécable n'y a rien
                # changé) et « = » venait se coller à l'indice.
                'rétention  <tspan font-style="italic">t</tspan>'
                '<tspan font-size="7" dy="2.5">NE,NE</tspan>'
                f'<tspan dy="-2.5" dx="3.5">= {_pct(d["retention"])}</tspan>',
                f"{_fr(d['stays'])} voix",
                highlight=not anchored,
                width_hint=84,
            ),
            # Seule flèche SORTANTE : sa destination, les qualifiés du second
            # tour, n'est pas dessinée — elle quitte le cadre, en pointillés.
            # Étiquette courte à dessein : sa pastille de fond masque le trait
            # qu'elle recouvre, et une étiquette aussi longue que la flèche n'en
            # laissait voir que la pointe, détachée dans le vide.
            _flow(
                "M228 316 C340 342 410 360 496 368",
                336,
                352,
                f"mobilisation  {_pct(1 - d['retention'])}",
                f"{_fr(d['mobilised'])} voix  →  qualifiés",
                dashed=True,
            ),
        ]
    )

    solde_y = 296
    parts.extend(
        [
            # Étiquette posée au-dessus de la boîte de droite : le lecteur voit
            # d'un coup ce qui est fixé (encadré) et ce qui en sort.
            f'<text class="{"accent" if anchored else "muted"}" x="{centre}" '
            'y="164" text-anchor="middle" font-size="9.4" font-style="italic">'
            + ("visé" if anchored else "déduit")
            + "</text>",
            f'<text class="ink" x="{centre}" y="{solde_y}" text-anchor="middle" '
            f'font-size="14" font-weight="700">solde net : {_fr(net, sign=True)} '
            "voix</text>",
            f'<text class="muted" x="{centre}" y="{solde_y + 17}" '
            'text-anchor="middle" font-size="9.8">'
            + (
                "imposé par la cible de participation"
                if anchored
                else "déduit des quatre taux ci-contre"
            )
            + "</text>",
            f'<line x1="24" y1="{height - 40}" x2="{width - 24}" y2="{height - 40}" '
            'class="rule" stroke-width="1"/>',
            f'<text class="muted" x="24" y="{height - 21}" font-size="9.7" '
            'font-style="italic">'
            + (
                "Encadré : le réservoir visé. Tous les flux vers les non-exprimés "
                "sont ajustés conjointement."
                if anchored
                else "Encadré : le taux que l’on fixe. Le réservoir du second "
                "tour et le solde en sont déduits par comptabilité."
            )
            + "</text>",
        ]
    )

    label = (
        "Le réservoir de non-exprimés visé par le modèle ancré et les flux "
        "ajustés conjointement pour l’atteindre"
        if anchored
        else "Un tirage du modèle national et le solde du réservoir des "
        "non-exprimés qu’il implique"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{label}, circonscription 5908">'
        f"{''.join(parts)}</svg>\n"
    )


def build_non_expressed_balance_svg() -> str:
    """Modèle national : on fixe `t_NE,NE`, le réservoir en découle."""
    return _render(_draw_balance(), anchored=False)


def build_non_expressed_anchored_svg() -> str:
    """Modèle ancré : on vise le réservoir, `t_NE,NE` en est déduit."""
    return _render(_solve_balance(), anchored=True)


if __name__ == "__main__":
    build_non_expressed_balance_svg()
    build_non_expressed_anchored_svg()
