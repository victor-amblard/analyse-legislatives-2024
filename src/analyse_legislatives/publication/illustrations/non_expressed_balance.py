"""Solde du réservoir des non-exprimés, entre les deux tours — un exemple.

Les flux BRUTS (qui se mobilise, qui démobilise) ne sont jamais identifiables
séparément à partir des seuls résultats agrégés : c'est l'inférence écologique,
déjà centrale ailleurs dans le billet. Seul le SOLDE (la différence entre les
deux réservoirs) est réellement observé. Cette figure le dit visuellement : les
deux flèches en pointillés n'affichent aucun nombre, seule la flèche du solde
en fait un.

Circonscription 5908 (Nord, duel NFP+/RN+) : chiffres recalculés à la main
depuis `analyse_legislatives.data` et les diagnostics d'`evaluate.py`
(`expressed-diagnostics-national*.csv`), pas inventés pour l'illustration.
"""

from analyse_legislatives.publication.illustrations._shared import theme_style

DISTRICT_LABEL = "Circonscription 5908 (Nord) — duel NFP+ / RN+"

FIRST_ROUND_VOTERS = 33_048
FIRST_ROUND_SHARE = 47.9

REAL_VOTERS = 34_629
REAL_SHARE = 50.2
REAL_NET = REAL_VOTERS - FIRST_ROUND_VOTERS  # +1 581

UNANCHORED_NET = 29_397 - FIRST_ROUND_VOTERS  # -3 650, modèle « national »


def _fr(n: int, *, sign: bool = False) -> str:
    """Sépare les milliers par une espace, à la française."""
    text = f"{n:+,}" if sign else f"{n:,}"
    return text.replace(",", " ")


def build_non_expressed_balance_svg() -> str:
    width, height = 760, 380
    box_w, box_h, box_y = 200, 96, 128
    box1_x, box2_x = 40, width - 40 - box_w
    mid_y = box_y + box_h / 2

    parts = [
        theme_style(),
        """<defs>
        <marker id="balance-arrow" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0L10 5L0 10Z" class="muted"/></marker>
        <marker id="balance-arrow-accent" viewBox="0 0 10 10" refX="8" refY="5"
          markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0 0L10 5L0 10Z" class="accent"/></marker>
        </defs>""",
        f'<rect class="surface" width="{width}" height="{height}"/>',
        '<text class="ink" x="24" y="29" font-size="17" font-weight="650">'
        "Non-exprimés : ce qui sort, ce qui entre, ce qui reste</text>",
        f'<text class="muted" x="24" y="49" font-size="11.5">{DISTRICT_LABEL}, '
        "2nd tour réel</text>",
        # Deux flèches en pointillés, chacune LOCALE à sa boîte : elles quittent
        # ou rejoignent les partis qualifiés/éliminés (non dessinés, pour ne pas
        # surcharger un schéma voulu simple) sans jamais se croiser — chaque
        # étiquette est cadrée au-dessus de sa propre flèche, jamais sur elle.
        '<text class="muted" x="60" y="66" font-size="10">sortie : mobilisation '
        "→ qualifiés</text>",
        '<path d="M150 128 C155 105 130 90 100 82" fill="none" class="muted" '
        'stroke-width="1.6" stroke-dasharray="3 3" marker-end="url(#balance-arrow)"/>',
        '<text class="muted" x="700" y="66" text-anchor="end" font-size="10">'
        "démobilisation → non-exprimés : entrée</text>",
        '<path d="M660 82 C630 90 605 105 610 128" fill="none" class="muted" '
        'stroke-width="1.6" stroke-dasharray="3 3" marker-end="url(#balance-arrow)"/>',
    ]

    boxes = [
        (
            box1_x,
            "Non-exprimés — 1er tour",
            f"{_fr(FIRST_ROUND_VOTERS)} voix",
            f"{FIRST_ROUND_SHARE:.1f} % des inscrits",
        ),
        (
            box2_x,
            "Non-exprimés — 2nd tour (réel)",
            f"{_fr(REAL_VOTERS)} voix",
            f"{REAL_SHARE:.1f} % des inscrits",
        ),
    ]
    for x, title, value, subtitle in boxes:
        parts.extend(
            [
                f'<rect class="frame" x="{x}" y="{box_y}" width="{box_w}" '
                f'height="{box_h}" rx="6" stroke-width="1"/>',
                f'<text class="ink" x="{x + box_w / 2}" y="{box_y + 24}" '
                f'text-anchor="middle" font-size="12" font-weight="650">{title}</text>',
                f'<text class="accent" x="{x + box_w / 2}" y="{box_y + 54}" '
                f'text-anchor="middle" font-size="19" font-weight="700">{value}</text>',
                f'<text class="muted" x="{x + box_w / 2}" y="{box_y + 76}" '
                f'text-anchor="middle" font-size="11">{subtitle}</text>',
            ]
        )

    # Flèche du solde : la seule quantité réellement observée — pas de
    # pointillés, trait accent, pour la distinguer visuellement des deux
    # flèches brutes ci-dessus.
    net_y = mid_y + 46
    parts.extend(
        [
            f'<line x1="{box1_x + box_w + 6}" y1="{net_y}" '
            f'x2="{box2_x - 6}" y2="{net_y}" class="accent-line" '
            'stroke-width="2.4" marker-end="url(#balance-arrow-accent)"/>',
            f'<text class="accent" x="380" y="{net_y - 12}" text-anchor="middle" '
            f'font-size="13" font-weight="700">solde net observé : '
            f"{_fr(REAL_NET, sign=True)} voix (+2,3 pts)</text>",
            f'<text class="muted" x="380" y="{net_y + 20}" text-anchor="middle" '
            'font-size="10.5">le réservoir grossit légèrement, malgré sa taille : '
            "la participation n’a pas rebondi</text>",
        ]
    )

    parts.extend(
        [
            f'<line x1="24" y1="{net_y + 42}" x2="{width - 24}" y2="{net_y + 42}" '
            'class="rule" stroke-width="1"/>',
            f'<text class="muted" x="24" y="{net_y + 62}" font-size="10" '
            'font-style="italic">Les flux bruts (qui se mobilise, qui démobilise) '
            "ne sont pas identifiables séparément à partir des seuls résultats "
            "agrégés — seul le solde l’est.</text>",
            f'<text class="muted" x="24" y="{net_y + 82}" font-size="10">'
            "Pour comparer : un modèle qui suppose la mobilisation proportionnelle "
            "au réservoir (sans ancrage) aurait prédit un solde de</text>",
            f'<text class="muted" x="24" y="{net_y + 99}" font-size="10">'
            f"{_fr(UNANCHORED_NET, sign=True)} voix — de sens opposé, et bien plus "
            "large.</text>",
        ]
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Solde du réservoir des non-exprimés entre les deux '
        f'tours, circonscription 5908">{"".join(parts)}</svg>\n'
    )


if __name__ == "__main__":
    build_non_expressed_balance_svg()
