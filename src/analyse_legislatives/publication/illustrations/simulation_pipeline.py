"""Swimlane diagram of one simulation at national and district scales."""

from xml.sax.saxutils import escape

from analyse_legislatives.config import DEFAULT_SEED, DEFAULT_TRANSFER_ORDERINGS
from analyse_legislatives.models import build
from analyse_legislatives.parties import PoliticalFamily, label
from analyse_legislatives.publication.illustrations._shared import theme_style

NATIONAL = "#7057c7"
LOCAL = "#1f8a70"
AGGREGATE = "#2a78d6"
CARD_WIDTH = 250
CARD_HEIGHT = 122


def _ordering_example() -> tuple[str, str]:
    """Short labels derived from one configured NFP+ linear extension."""
    source = PoliticalFamily.NFPx
    tiers = DEFAULT_TRANSFER_ORDERINGS[source]
    partial = "  ›  ".join(
        label(tier[0]) if len(tier) == 1 else f"{len(tier)} choix ex æquo"
        for tier in tiers
    )
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
    colour: str,
) -> str:
    line_svg = "".join(
        f'<text class="muted" x="{x + 18}" y="{y + 53 + i * 17}" '
        f'font-size="10.2">{escape(line)}</text>'
        for i, line in enumerate(lines)
    )
    return (
        f'<rect class="surface" x="{x}" y="{y}" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" '
        f'rx="8" stroke="{colour}" stroke-opacity="0.42"/>'
        f'<circle cx="{x + 20}" cy="{y + 21}" r="13" fill="{colour}"/>'
        f'<text x="{x + 20}" y="{y + 25}" text-anchor="middle" font-size="10" '
        f'font-weight="700" fill="white">{number}</text>'
        f'<text class="ink" x="{x + 42}" y="{y + 26}" font-size="12.3" '
        f'font-weight="650">{escape(title)}</text>'
        f"{line_svg}"
    )


def _arrow(x1: int, y1: int, x2: int, y2: int, colour: str) -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{colour}" stroke-opacity="0.7" stroke-width="1.7" '
        f'marker-end="url(#arrow-{colour[1:]})"/>'
    )


def build_simulation_pipeline_svg() -> str:
    width, height = 900, 650
    partial, total = _ordering_example()
    columns = (56, 325, 594)

    parts = [
        theme_style(),
        f"""<defs>
        <marker id="arrow-{NATIONAL[1:]}" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10Z" fill="{NATIONAL}"/></marker>
        <marker id="arrow-{LOCAL[1:]}" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10Z" fill="{LOCAL}"/></marker>
        <marker id="arrow-{AGGREGATE[1:]}" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10Z" fill="{AGGREGATE}"/></marker>
        </defs>""",
        f'<rect class="surface" width="{width}" height="{height}"/>',
        '<text class="ink" x="24" y="29" font-size="17" font-weight="650">Une simulation, à deux échelles</text>',
        '<text class="muted" x="24" y="49" font-size="11.5">L’incertitude commune est tirée une fois ; les opérations locales sont ensuite répétées dans chaque circonscription.</text>',
        f'<rect x="24" y="68" width="852" height="184" rx="11" fill="{NATIONAL}" fill-opacity="0.07"/>',
        f'<text x="42" y="91" font-size="10" font-weight="700" letter-spacing="0.08em" fill="{NATIONAL}">UNE FOIS PAR SIMULATION · ÉCHELLE NATIONALE</text>',
        '<text class="muted" x="852" y="91" text-anchor="end" font-size="9.5">partagé par toutes les circonscriptions</text>',
        f'<rect x="24" y="269" width="852" height="200" rx="11" fill="{LOCAL}" fill-opacity="0.07"/>',
        f'<text x="42" y="293" font-size="10" font-weight="700" letter-spacing="0.08em" fill="{LOCAL}">RÉPÉTÉ DANS CHAQUE CIRCONSCRIPTION · ÉCHELLE LOCALE</text>',
        '<text class="muted" x="852" y="293" text-anchor="end" font-size="9.5">une fois par circonscription simulée</text>',
    ]

    national_y = 108
    parts.extend(
        [
            _card(
                columns[0],
                national_y,
                1,
                "Paramètres globaux",
                (
                    "alpha règle la dispersion des reports",
                    "le tilt répartit la remobilisation",
                    "démobilisation ; rétention (modèle national)",
                    "lambda dose national / local (noyau)",
                ),
                NATIONAL,
            ),
            _card(
                columns[1],
                national_y,
                2,
                "Ordres de préférence",
                (
                    "un ordre partiel par parti source",
                    f"NFP+ : {partial}",
                    "permutation aléatoire des seuls ex æquo",
                    f"un tirage : {total}",
                ),
                NATIONAL,
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
                NATIONAL,
            ),
            _arrow(307, 169, 320, 169, NATIONAL),
            _arrow(576, 169, 589, 169, NATIONAL),
        ]
    )

    local_y = 310
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
                LOCAL,
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
                    "ancré : résoudre les flux depuis la cible",
                ),
                LOCAL,
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
                LOCAL,
            ),
            _arrow(589, 371, 580, 371, LOCAL),
            _arrow(320, 371, 311, 371, LOCAL),
            f'<path d="M181 432 C181 483 247 497 267 511" fill="none" stroke="{AGGREGATE}" stroke-opacity="0.7" stroke-width="1.8" marker-end="url(#arrow-{AGGREGATE[1:]})"/>',
            f'<rect x="272" y="501" width="356" height="84" rx="10" fill="{AGGREGATE}" fill-opacity="0.09" stroke="{AGGREGATE}" stroke-opacity="0.48"/>',
            f'<circle cx="296" cy="525" r="13" fill="{AGGREGATE}"/>',
            '<text x="296" y="529" text-anchor="middle" font-size="10" font-weight="700" fill="white">7</text>',
            '<text class="ink" x="318" y="530" font-size="12.5" font-weight="650">Retour à l’échelle nationale</text>',
            '<text class="muted" x="296" y="555" font-size="10.5">Compter les vainqueurs locaux par parti donne un vecteur de sièges.</text>',
            '<text class="muted" x="296" y="572" font-size="10.2">Il s’agit d’un tirage de la distribution jointe nationale.</text>',
            f'<path d="M719 230 C719 269 719 280 719 303" fill="none" stroke="{LOCAL}" stroke-opacity="0.65" stroke-width="1.8" marker-end="url(#arrow-{LOCAL[1:]})"/>',
            '<text class="muted" x="730" y="275" font-size="9.3">entrée dans la boucle locale</text>',
            '<text class="muted" x="450" y="632" text-anchor="middle" font-size="10">Répéter la simulation complète permet d’approcher la distribution prédictive jointe des sièges.</text>',
        ]
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Simulation séparée entre échelles nationale et locale">'
        f'{"".join(parts)}</svg>\n'
    )
