import polars as pl

from analyse_legislatives.publication.sources import load_pollster_ranges


def test_pollster_ranges_are_complete_and_sourced():
    data = load_pollster_ranges()

    assert data.get_column("pollster").n_unique() == 4
    assert data.get_column("party").n_unique() == 5
    assert data.height == 20
    assert data.get_column("source_url").str.starts_with("https://").all()
    assert data.select((pl.col("low") <= pl.col("high")).all()).item()
    assert (
        data.group_by("party")
        .agg(pl.col("actual").n_unique())
        .get_column("actual")
        .eq(1)
        .all()
    )
