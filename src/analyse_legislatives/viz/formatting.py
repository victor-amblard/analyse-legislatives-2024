"""Mise en forme des nombres affichés (français : espace comme séparateur de
milliers, virgule jamais utilisée ici puisque les décimales sont rares)."""

import polars as pl

INTERVAL_LEVEL = 0.90
"""Niveau des intervalles affichés partout dans l'app. Les bornes 5 % / 95 % en
découlent, plutôt que d'être écrites en dur à chaque appel."""


def format_number(value) -> str:
    """Entier avec séparateur de milliers à la française."""
    return f"{value:,.0f}".replace(",", " ")


def interval_bounds(series: pl.Series, level: float = INTERVAL_LEVEL):
    """Bornes de l'intervalle central au niveau `level`."""
    tail = (1 - level) / 2
    return series.quantile(tail), series.quantile(1 - tail)


def format_interval(
    series: pl.Series,
    suffix: str = "",
    decimals: int = 1,
    level: float = INTERVAL_LEVEL,
) -> str:
    """Intervalle central, tel qu'affiché sous les métriques."""
    lo, hi = interval_bounds(series, level)
    return f"[{lo:.{decimals}f}{suffix} — {hi:.{decimals}f}{suffix}]"
