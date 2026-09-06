"""Conceptual overview of one simulation at national and district scales."""

from xml.sax.saxutils import escape

from analyse_legislatives.publication.illustrations._shared import theme_style


def _card(
    x: int,
    y: int,
    width: int,
    height: int,
    number: int | None,
    title: str,
    lines: tuple[str, ...],
    kind: str,
    *,
    symbols: str | None = None,
) -> str:
    """Draw a compact card; colour encodes its role, not a political family."""
    title_x = x + 18
    if number is None:
        heading = (
            f'<text class="ink" x="{title_x}" y="{y + 29}" font-size="13" '
            f'font-weight="680">{escape(title)}</text>'
        )
    else:
        heading = (
            f'<text x="{title_x}" y="{y + 29}" font-size="13">'
            f'<tspan class="{kind}-ink" font-weight="750">{number}.</tspan> '
            f'<tspan class="ink" font-weight="680">{escape(title)}</tspan></text>'
        )

    line_svg = "".join(
        f'<text class="muted" x="{title_x}" y="{y + 58 + i * 19}" '
        f'font-size="10.7">{escape(line)}</text>'
        for i, line in enumerate(lines)
    )
    symbol_svg = ""
    if symbols:
        symbol_svg = (
            f'<text class="{kind}-ink" x="{x + width - 16}" y="{y + height - 13}" '
            f'text-anchor="end" font-size="9.5" font-weight="650">{escape(symbols)}</text>'
        )

    return (
        f'<rect class="card {kind}-card" x="{x}" y="{y}" width="{width}" '
        f'height="{height}" rx="8" stroke-width="1"/>'
        f'<rect class="{kind}-bar" x="{x}" y="{y}" width="5" height="{height}" '
        f'rx="2.5"/>'
        f"{heading}{line_svg}{symbol_svg}"
    )


def _arrow(x1: int, y1: int, x2: int, y2: int, *, css: str = "arrow") -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'class="{css}" stroke-width="1.6" marker-end="url(#pipeline-arrow)"/>'
    )


def _lane_label(y: int, eyebrow: str, label: str, note: str) -> str:
    return (
        f'<text class="accent" x="28" y="{y}" font-size="9.5" '
        f'font-weight="750" letter-spacing=".9">{escape(eyebrow)}</text>'
        f'<text class="ink" x="230" y="{y}" font-size="11.5" '
        f'font-weight="680">{escape(label)}</text>'
        f'<text class="muted" x="932" y="{y}" text-anchor="end" '
        f'font-size="10">{escape(note)}</text>'
    )


def build_simulation_pipeline_svg() -> str:
    width, height = 960, 760
    parts = [
        theme_style(),
        """<style>
        .card{stroke-width:1}
        .hypothesis-card{fill:#efebfa;stroke:#c0b3e0}.hypothesis-bar{fill:#5b3f93}
        .hypothesis-ink{fill:#432a70}
        .data-card{fill:#f2f4f7;stroke:#c9cfd8}.data-bar{fill:#7b8492}
        .data-ink{fill:#646d7a}
        .local-card{fill:#fff5e9;stroke:#e4bc8b}.local-bar{fill:#c77b2b}
        .local-ink{fill:#a45f19}
        .result-card{fill:#eef8ef;stroke:#a8cfaa}.result-bar{fill:#438c4b}
        .result-ink{fill:#34743b}
        .arrow{stroke:#89919e}.input-arrow{stroke:#a0a7b2;stroke-dasharray:4 3}
        .lane{fill:#f7f8fa}.repeat{fill:#efebfa;stroke:#b3a6d8}
        @media(prefers-color-scheme:dark){
          .hypothesis-card{fill:#221a33;stroke:#574a7d}.hypothesis-bar{fill:#b09ce8}
          .hypothesis-ink{fill:#c4b6ef}
          .data-card{fill:#22262d;stroke:#515864}.data-bar{fill:#8993a2}
          .data-ink{fill:#aeb5c0}
          .local-card{fill:#342719;stroke:#7f5a31}.local-bar{fill:#dfa15d}
          .local-ink{fill:#ebb778}
          .result-card{fill:#1c2f20;stroke:#4e7653}.result-bar{fill:#71b879}
          .result-ink{fill:#8bca91}
          .arrow{stroke:#727b89}.input-arrow{stroke:#6b7481}
          .lane{fill:#191c21}.repeat{fill:#221a33;stroke:#7a6ea8}
        }
        </style>""",
        """<defs>
        <marker id="pipeline-arrow" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0L10 5L0 10Z" fill="#89919e"/></marker>
        </defs>""",
        f'<rect class="surface" width="{width}" height="{height}"/>',
        '<text class="ink" x="28" y="34" font-size="18" font-weight="700">Une simulation, du national aux circonscriptions</text>',
        '<text class="muted" x="28" y="56" font-size="11.7">Un scénario commun est tiré, adapté aux données locales, puis agrégé en sièges.</text>',
        '<line x1="28" y1="78" x2="932" y2="78" class="rule" stroke-width="1"/>',
        _lane_label(
            101,
            "ÉCHELLE NATIONALE",
            "Construire un scénario commun",
            "tiré une fois par simulation",
        ),
        '<rect class="lane" x="28" y="115" width="904" height="154" rx="10"/>',
        _card(
            50,
            136,
            220,
            112,
            None,
            "Hypothèses choisies",
            (
                "ordres partiels de préférence",
                "plages de valeurs plausibles",
                "structure des variations locales",
            ),
            "hypothesis",
        ),
        _card(
            320,
            136,
            260,
            112,
            1,
            "Tirer un scénario plausible",
            (
                "tirer une valeur pour chaque paramètre",
                "départager au hasard les ex æquo",
                "garder un même scénario national",
            ),
            "hypothesis",
        ),
        _card(
            630,
            136,
            270,
            112,
            2,
            "Construire le scénario national",
            (
                "calculer les probabilités de report",
                "fixer l’évolution de la participation",
                "former une référence nationale commune",
            ),
            "hypothesis",
        ),
        _arrow(276, 192, 309, 192),
        _arrow(586, 192, 619, 192),
        '<line x1="28" y1="287" x2="932" y2="287" class="rule" stroke-width="1"/>',
        _lane_label(
            310,
            "ÉCHELLE LOCALE",
            "Adapter et simuler les voix",
            "répété dans chacune des 501 circonscriptions",
        ),
        '<rect class="lane" x="28" y="324" width="904" height="258" rx="10"/>',
        '<rect class="card data-card" x="50" y="338" width="850" height="76" '
        'rx="8" stroke-width="1"/>',
        '<rect class="data-bar" x="50" y="338" width="5" height="76" rx="2.5"/>',
        '<text class="ink" x="70" y="368" font-size="12.5" '
        'font-weight="680">Entrées de chaque circonscription</text>',
        '<text class="muted" x="70" y="390" font-size="9.8">un scénario simulé + les données observées</text>',
        '<rect class="hypothesis-card" x="292" y="353" width="132" height="40" rx="20"/>',
        '<text class="hypothesis-ink" x="358" y="377" text-anchor="middle" '
        'font-size="9.5" font-weight="650">scénario national</text>',
        '<rect class="surface" x="440" y="353" width="136" height="40" rx="20"/>',
        '<text class="data-ink" x="508" y="377" text-anchor="middle" '
        'font-size="9.3" font-weight="650">candidats au 2e tour</text>',
        '<rect class="surface" x="592" y="353" width="136" height="40" rx="20"/>',
        '<text class="data-ink" x="660" y="371" text-anchor="middle" '
        'font-size="9.1" font-weight="650">participation</text>',
        '<text class="data-ink" x="660" y="383" text-anchor="middle" '
        'font-size="8.8">du premier tour</text>',
        '<rect class="surface" x="744" y="353" width="136" height="40" rx="20"/>',
        '<text class="data-ink" x="812" y="371" text-anchor="middle" '
        'font-size="9.1" font-weight="650">réservoirs de voix</text>',
        '<text class="data-ink" x="812" y="383" text-anchor="middle" '
        'font-size="8.8">du premier tour</text>',
        _card(
            50,
            444,
            260,
            116,
            3,
            "Adapter à la circonscription",
            (
                "conserver les candidats présents",
                "ajouter un écart géographique local",
                "obtenir les reports locaux",
            ),
            "local",
        ),
        _card(
            350,
            444,
            260,
            116,
            4,
            "Ancrer la participation",
            (
                "partir du taux du premier tour",
                "ajouter une évolution nationale",
                "ajuster les flux non exprimés",
            ),
            "local",
        ),
        _card(
            650,
            444,
            250,
            116,
            5,
            "Simuler les voix",
            (
                "répartir chaque réservoir",
                "additionner les voix par candidat",
                "désigner le vainqueur local",
            ),
            "local",
        ),
        '<path d="M765 248 V275 H205 V327" fill="none" '
        'class="arrow" stroke-width="1.6" marker-end="url(#pipeline-arrow)"/>',
        '<path d="M180 414 L180 433" fill="none" class="input-arrow" '
        'stroke-width="1.6" marker-end="url(#pipeline-arrow)"/>',
        '<path d="M480 414 L480 433" fill="none" class="input-arrow" '
        'stroke-width="1.6" marker-end="url(#pipeline-arrow)"/>',
        '<path d="M775 414 L775 433" fill="none" class="input-arrow" '
        'stroke-width="1.6" marker-end="url(#pipeline-arrow)"/>',
        _arrow(316, 502, 339, 502),
        _arrow(616, 502, 639, 502),
        '<line x1="28" y1="600" x2="932" y2="600" class="rule" stroke-width="1"/>',
        _lane_label(
            623,
            "RETOUR AU NATIONAL",
            "Produire une projection en sièges",
            "une sortie complète par simulation",
        ),
        _card(
            180,
            643,
            390,
            82,
            6,
            "Agréger les 501 vainqueurs",
            ("compter les sièges obtenus par chaque groupe politique",),
            "result",
        ),
        '<path d="M775 560 V588 H205 V632" fill="none" '
        'class="arrow" stroke-width="1.6" marker-end="url(#pipeline-arrow)"/>',
        '<rect class="repeat" x="614" y="650" width="286" height="66" rx="33" stroke-width="1"/>',
        '<text class="hypothesis-ink" x="757" y="676" text-anchor="middle" '
        'font-size="11.2" font-weight="700">Répéter 3 000 fois</text>',
        '<text class="muted" x="757" y="697" text-anchor="middle" font-size="10.2">distribution et intervalles prédictifs</text>',
        _arrow(576, 684, 603, 684),
    ]

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Étapes d’une simulation, de l’échelle nationale aux circonscriptions puis au nombre de sièges">'
        f"{''.join(parts)}</svg>\n"
    )
