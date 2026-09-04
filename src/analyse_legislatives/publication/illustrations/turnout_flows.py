from analyse_legislatives.publication.illustrations._shared import theme_style


def build_turnout_flows_svg() -> str:
    width, height = 760, 350
    parts = [
        theme_style(),
        """<defs>
        <marker id="arrow-blue" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#2a78d6"/></marker>
        <marker id="arrow-orange" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#b56824"/></marker>
        <marker id="arrow-grey" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10Z" fill="#7b818c"/></marker>
        </defs>""",
        f'<rect class="surface" width="{width}" height="{height}"/>',
        '<text class="ink" x="20" y="28" font-size="16" font-weight="600">Flux de voix entre les deux tours</text>',
        '<text class="muted" x="20" y="48" font-size="11">Chaque réservoir du premier tour est réparti entre candidats qualifiés et suffrages non exprimés.</text>',
        '<text class="muted" x="108" y="78" text-anchor="middle" font-size="10.5" font-weight="600">Premier tour</text>',
        '<text class="muted" x="650" y="78" text-anchor="middle" font-size="10.5" font-weight="600">Second tour</text>',
    ]
    boxes = [
        (24, 92, 168, 58, "#2a78d6", "Partis qualifiés", "LR, RN+"),
        (24, 181, 168, 58, "#b56824", "Partis éliminés", "ENS+, NFP+, DVG, DVD, DIV"),
        (24, 270, 168, 58, "#7b818c", "Non exprimés", ""),
        (578, 115, 158, 70, "#2a78d6", "Partis qualifiés", "suffrages exprimés"),
        (578, 249, 158, 70, "#7b818c", "Non exprimés", "abstention, blancs, nuls"),
    ]
    for x, y, w, h, colour, title, subtitle in boxes:
        parts.extend(
            [
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{colour}" fill-opacity="0.11" stroke="{colour}" stroke-opacity="0.72"/>',
                f'<text class="ink" x="{x + w / 2}" y="{y + 25}" text-anchor="middle" font-size="12" font-weight="600">{title}</text>',
                f'<text class="muted" x="{x + w / 2}" y="{y + 43}" text-anchor="middle" font-size="10">{subtitle}</text>',
            ]
        )
    flows = [
        (
            "M192 111 C340 92 438 101 578 136",
            "#2a78d6",
            "arrow-blue",
            295,
            99,
            "Fidélité  (1 − d)",
        ),
        (
            "M192 135 C338 161 440 245 578 271",
            "#2a78d6",
            "arrow-blue",
            286,
            153,
            "Démobilisation  d",
        ),
        (
            "M192 202 C343 177 443 158 578 151",
            "#b56824",
            "arrow-orange",
            292,
            184,
            "Reports vers les qualifiés",
        ),
        (
            "M192 226 C340 244 440 273 578 283",
            "#b56824",
            "arrow-orange",
            297,
            240,
            "Reports vers NON_EXPR",
        ),
        (
            "M192 287 C335 278 447 189 578 169",
            "#7b818c",
            "arrow-grey",
            298,
            272,
            "Mobilisation",
        ),
        (
            "M192 310 C340 333 445 324 578 300",
            "#7b818c",
            "arrow-grey",
            285,
            332,
            "Rétention",
        ),
    ]
    for path, colour, marker, text_x, text_y, label in flows:
        parts.append(
            f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="2.2" marker-end="url(#{marker})"/>'
            f'<rect class="surface" x="{text_x - 78}" y="{text_y - 12}" width="156" height="17" opacity="0.92"/>'
            f'<text class="ink" x="{text_x}" y="{text_y}" text-anchor="middle" font-size="10.5">{label}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Schéma des flux entre les deux tours">{"".join(parts)}</svg>\n'
    )


if __name__ == "__main__":
    build_turnout_flows_svg()
