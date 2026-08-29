"""Tabular sources consumed by publication figures and benchmarks."""

import polars as pl

from analyse_legislatives.config import DATA_DIR

POLLSTER_RANGES_PATH = DATA_DIR / "raw/pollsters/legislatives-2024-seat-ranges.csv"


def load_pollster_ranges() -> pl.DataFrame:
    """Load the sourced, five-block pre-election seat ranges."""
    data = pl.read_csv(POLLSTER_RANGES_PATH)
    duplicates = data.group_by("pollster", "party").len().filter(pl.col("len") != 1)
    if duplicates.height:
        raise ValueError(
            f"Expected one range per pollster and party in {POLLSTER_RANGES_PATH}."
        )
    inconsistent_truth = (
        data.group_by("party")
        .agg(pl.col("actual").n_unique().alias("n"))
        .filter(pl.col("n") != 1)
    )
    if inconsistent_truth.height:
        raise ValueError(
            f"Inconsistent actual results across sources in {POLLSTER_RANGES_PATH}."
        )
    return data
