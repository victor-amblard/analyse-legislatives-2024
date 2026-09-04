"""Swimlane diagram of one simulation at national and district scales."""

from xml.sax.saxutils import escape

from analyse_legislatives.config import DEFAULT_SEED, DEFAULT_TRANSFER_ORDERINGS
from analyse_legislatives.models import build
from analyse_legislatives.parties import PoliticalFamily, label
from analyse_legislatives.publication.illustrations._shared import theme_style

# Pas de couleur par échelle : national, local et l'agrégat final sont trois
# MOMENTS d'une même simulation, pas trois catégories à distinguer par teinte.
# Seul l'accent de marque du site (voir `theme_style`) marque la numérotation ;
# tout le reste — cadres, flèches — reste en encre et en gris.
CARD_WIDTH = 250
CARD_HEIGHT = 122


def _ordering_example() -> tuple[str, str]:
    """Short labels derived from one configured NFP+ linear extension."""
    source = PoliticalFamily.NFPx
    tiers = DEFAULT_TRANSFER_ORDERINGS[source]
    # Les 4 paliers de NFP+ mis bout à bout débordent la largeur de la carte —
    # même troncature que `total` juste en dessous, pour rester dans la carte.
    partial = "  ›  ".join(
        label(tier[0]) if len(tier) == 1 else f"{len(tier)} choix ex æquo"
        for tier in tiers[:3]
    )
    if len(tiers) > 3:
        partial += "  ›  …"
    extension = (
        build("national", seed=DEFAULT_SEED).draw_simulation().extensions[source]
    )
    total = "  ›  ".join(label(target) for target in extension[:3]) + "  ›  …"
    return partial, total


def _card(
    x: int,
    y: int,
    number: int,
    title: str,
    lines: tuple[str, ...],
) -> str:
    line_svg = "".join(
        f'<text class="muted" x="{x + 14}" y="{y + 53 + i * 17}" '
        f'font-size="10.2">{escape(line)}</text>'
        for i, line in enumerate(lines)
    )
    return (
        f'<rect class="frame" x="{x}" y="{y}" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" '
        f'rx="6" stroke-width="1"/>'
        f'<text x="{x + 14}" y="{y + 25}" font-size="12.3">'
        f'<tspan class="accent" font-weight="700">{number}.</tspan> '
        f'<tspan class="ink" font-weight="650">{escape(title)}</tspan></text>'
        f"{line_svg}"
    )


def _arrow(x1: int, y1: int, x2: int, y2: int) -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        'class="rule" stroke-width="1.5" marker-end="url(#pipeline-arrow)"/>'
    )


def build_simulation_pipeline_svg() -> str:
    width, height = 900, 650
    partial, total = _ordering_example()
    columns = (56, 325, 594)

    parts = [
        theme_style(),
        """<defs>
        <marker id="pipeline-arrow" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0L10 5L0 10Z" class="muted"/></marker>
        </defs>""",
        f'<rect class="surface" width="{width}" height="{height}"/>',
        '<text class="ink" x="24" y="29" font-size="17" font-weight="650">Une simulation, à deux échelles</text>',
        '<text class="muted" x="24" y="49" font-size="11.5">L’incertitude commune est tirée une fois ; les opérations locales sont ensuite répétées dans chaque circonscription.</text>',
        '<line x1="24" y1="76" x2="876" y2="76" class="rule" stroke-width="1"/>',
        '<text class="ink" x="24" y="94" font-size="11" font-weight="650">Tiré une fois par simulation</text>',
        '<text class="muted" x="852" y="94" text-anchor="end" font-size="9.5">partagé, ou dosé avec le local selon le noyau</text>',
        '<line x1="24" y1="277" x2="876" y2="277" class="rule" stroke-width="1"/>',
        '<text class="ink" x="24" y="295" font-size="11" font-weight="650">Répété dans chaque circonscription — échelle locale</text>',
        '<text class="muted" x="852" y="295" text-anchor="end" font-size="9.5">une fois par circonscription simulée</text>',
    ]

    national_y = 116
    parts.extend(
        [
            _card(
                columns[0],
                national_y,
                1,
                "Paramètres globaux",
                (
                    "alpha règle la dispersion des reports",
                    "tilt : remobilisation, locale sous noyau",
                    "démobilisation ; rétention (modèle national)",
                    "lambda, 2 rho (dépt/région) dosent le noyau",
                ),
            ),
            _card(
                columns[1],
                national_y,
                2,
                "Ordres de préférence",
                (
                    "un ordre partiel par parti source",
                    f"NFP+ : {partial}",
                    "ex æquo : permutation nationale ou locale",
                    f"un tirage : {total}",
                ),
            ),
            _card(
                columns[2],
                national_y,
                3,
                "Composante commune",
                (
                    "national : une uniforme par cellule",
                    "noyau : un facteur gaussien par cellule",
                    "un même tirage pour toutes les circonscriptions",
                    "les cellules sont tirées indépendamment",
                ),
            ),
            _arrow(307, 177, 320, 177),
            _arrow(576, 177, 589, 177),
        ]
    )

    local_y = 318
    parts.extend(
        [
            _card(
                columns[2],
                local_y,
                4,
                "Taux de report locaux",
                (
                    "noyau : ajouter un écart local corrélé",
                    "transformer en poids Gamma",
                    "classer les parts soumises à l’ordre",
                    "normaliser chaque ligne à 100 %",
                ),
            ),
            _card(
                columns[1],
                local_y,
                5,
                "Bulletin et participation",
                (
                    "ne garder que les candidats qualifiés",
                    "renormaliser les destinations restantes",
                    "ajouter rétention et non-expression",
                    "ancré : cible nationale + écart local corrélé",
                ),
            ),
            _card(
                columns[0],
                local_y,
                6,
                "Voix et vainqueur local",
                (
                    "prendre chaque réservoir du premier tour",
                    "ventiler ses voix par une multinomiale",
                    "additionner les voix par destination",
                    "le candidat arrivé en tête gagne",
                ),
            ),
            _arrow(589, 379, 580, 379),
            _arrow(320, 379, 311, 379),
            '<path d="M181 440 C181 491 247 505 267 519" fill="none" '
            'class="rule" stroke-width="1.5" marker-end="url(#pipeline-arrow)"/>',
            '<rect x="272" y="509" width="356" height="84" rx="6" '
            'class="frame" stroke-width="1"/>',
            '<text x="286" y="533" font-size="12.5">'
            '<tspan class="accent" font-weight="700">7.</tspan> '
            '<tspan class="ink" font-weight="650">Retour à l’échelle nationale</tspan></text>',
            '<text class="muted" x="286" y="558" font-size="10.5">Compter les vainqueurs locaux par parti donne un vecteur de sièges.</text>',
            '<text class="muted" x="286" y="575" font-size="10.2">Il s’agit d’un tirage de la distribution jointe nationale.</text>',
            '<path d="M719 238 C719 277 719 288 719 311" fill="none" '
            'class="rule" stroke-width="1.5" marker-end="url(#pipeline-arrow)"/>',
            '<text class="muted" x="730" y="283" font-size="9.3">entrée dans la boucle locale</text>',
            '<text class="muted" x="450" y="632" text-anchor="middle" font-size="10">Répéter la simulation complète permet d’approcher la distribution prédictive jointe des sièges.</text>',
        ]
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Simulation séparée entre échelles nationale et locale">'
        f'{"".join(parts)}</svg>\n'
    )
