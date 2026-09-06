"""Agrégations : sièges, suffrages exprimés, tableaux par circonscription."""

import numpy as np
import polars as pl
import pytest

from analyse_legislatives import projections, simulation
from analyse_legislatives.parties import NON_EXPRIMES, DESTINATIONS, SPECTRUM_LABELS

NFP = DESTINATIONS.index("NFP+")
RN = DESTINATIONS.index("RN+")
ABS_COL = DESTINATIONS.index(NON_EXPRIMES)


def cube_from(rows: list[list[dict]]) -> np.ndarray:
    """Construit un cube à partir de `{destination: voix}` par (simulation,
    circonscription) — plus lisible qu'un littéral numpy à trois niveaux."""
    return np.array(
        [[[row.get(d, 0) for d in DESTINATIONS] for row in simu] for simu in rows],
        dtype=np.int64,
    )


class TestSeats:
    def test_winner_is_the_party_with_most_votes(self):
        cube = cube_from([[{"NFP+": 100, "RN+": 90}], [{"NFP+": 80, "RN+": 95}]])
        assert projections.winners_by_simulation(cube).tolist() == [[NFP], [RN]]

    def test_abstention_never_wins(self):
        """NON_EXPRIMES domine largement mais n'élit personne."""
        cube = cube_from([[{"NFP+": 100, "RN+": 90, NON_EXPRIMES: 5_000}]])
        assert projections.winners_by_simulation(cube).tolist() == [[NFP]]

    def test_seats_sum_to_districts_plus_first_round(self):
        cube = cube_from(
            [
                [{"NFP+": 100, "RN+": 90}, {"NFP+": 10, "RN+": 80}],
                [{"NFP+": 100, "RN+": 90}, {"NFP+": 90, "RN+": 80}],
            ]
        )
        seats = projections.seats_by_simulation(cube, {"LR": 3})
        assert seats.select(pl.sum_horizontal(pl.all()).eq(2 + 3)).to_series().all()

    def test_columns_follow_the_political_spectrum(self):
        cube = cube_from([[{"NFP+": 100, "RN+": 90}]])
        seats = projections.seats_by_simulation(cube, {})
        assert list(seats.columns) == SPECTRUM_LABELS
        assert all(isinstance(c, str) for c in seats.columns)

    def test_first_round_seats_are_added_to_every_simulation(self):
        cube = cube_from([[{"NFP+": 100, "RN+": 90}], [{"NFP+": 100, "RN+": 90}]])
        seats = projections.seats_by_simulation(cube, {"RN+": 7})
        assert seats["RN+"].to_list() == [7, 7]
        assert seats["NFP+"].to_list() == [1, 1]


class TestExpressedShare:
    def test_expressed_is_the_complement_of_abstention(self, districts):
        cube = cube_from(
            [[{"NFP+": 600, NON_EXPRIMES: 400}, {"NFP+": 800, NON_EXPRIMES: 200}]]
        )
        share = projections.expressed_share_by_simulation(
            cube, districts, {"01": 1_000, "02": 1_000}
        )
        assert share.to_list() == pytest.approx([100 - 600 / 2000 * 100])

    def test_district_rate_uses_its_own_registered_voters(self):
        cube = cube_from(
            [[{"NFP+": 700, NON_EXPRIMES: 300}], [{"NFP+": 500, NON_EXPRIMES: 500}]]
        )
        rate = projections.district_expressed_rate(cube, 0, inscrits=1_000)
        assert rate.to_list() == pytest.approx([70.0, 50.0])

    def test_seats_vs_non_expressed_aggregates_one_point_bins(self):
        seats = pl.DataFrame({"NFP+": [100, 120, 140], "RN+": [200, 180, 160]})
        conditional = projections.conditional_seats_by_non_expressed(
            seats, pl.Series([69.8, 69.4, 60.0])
        )

        nfp_30 = conditional.filter(
            (pl.col("parti") == "NFP+") & (pl.col("tranche_basse") == 30)
        ).row(0, named=True)
        assert nfp_30["sieges_medians"] == pytest.approx(110)
        assert nfp_30["simulations"] == 2
        assert nfp_30["non_exprimés"] == pytest.approx(30.5)

    def test_seats_vs_non_expressed_rejects_mismatched_simulations(self):
        with pytest.raises(ValueError, match="une ligne par simulation"):
            projections.conditional_seats_by_non_expressed(
                pl.DataFrame({"NFP+": [100, 120]}), pl.Series([70.0])
            )


class TestDistrictSummary:
    @pytest.fixture
    def summary(self):
        cube = cube_from(
            [
                [{"NFP+": 100, "RN+": 90, NON_EXPRIMES: 10}],
                [{"NFP+": 120, "RN+": 80, NON_EXPRIMES: 10}],
                [{"NFP+": 70, "RN+": 130, NON_EXPRIMES: 10}],
                [{"NFP+": 110, "RN+": 95, NON_EXPRIMES: 10}],
            ]
        )
        return projections.district_summary(cube, 0)

    def test_sorted_by_descending_median(self, summary):
        assert summary["parti"].to_list() == ["NFP+", "RN+"]

    def test_drops_parties_that_are_not_running(self, summary):
        """Un duel affiche deux lignes, pas cinq dont trois de zéros."""
        assert len(summary) == 2

    def test_win_rates_sum_to_one_hundred(self, summary):
        """Une seule victoire par simulation : les ex aequo étaient auparavant
        comptés pour tous les partis à égalité, et le total dépassait 100 %."""
        assert summary["% de victoires"].sum() == pytest.approx(100.0)

    def test_win_rate_counts_simulations(self, summary):
        rates = dict(summary.select("parti", "% de victoires").iter_rows())
        assert rates["NFP+"] == pytest.approx(75.0)
        assert rates["RN+"] == pytest.approx(25.0)


class TestMedianScenario:
    def test_returns_an_actually_observed_row(self):
        """C'est tout l'intérêt : une médiane marginale par colonne ne
        correspond à aucun scénario réellement simulé."""
        df = pl.DataFrame({"a": [1, 5, 9], "b": [9, 5, 1]})
        result = projections.closest_to_marginal_median(df)
        assert tuple(result.values()) in df.rows()

    def test_picks_the_closest_row_to_the_marginal_median(self):
        df = pl.DataFrame({"a": [0, 5, 100], "b": [0, 5, 100]})
        assert list(projections.closest_to_marginal_median(df).values()) == [5, 5]


class TestLongFrame:
    def test_roundtrip_preserves_every_vote(self, districts):
        cube = simulation.run(
            __import__("analyse_legislatives.models", fromlist=["build"]).build(
                "kernel_anchored", seed=0
            ),
            districts,
            3,
        )
        long = simulation.to_long_frame(cube, districts)
        assert len(long) == cube.size
        assert long["votes"].sum() == cube.sum()
