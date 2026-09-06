"""Contrats minimaux des données qui alimentent le modèle."""

from analyse_legislatives.data import load_full_results, load_second_round_results
from analyse_legislatives.parties import DESTINATIONS, PoliticalFamily


def test_first_round_loader_builds_complete_districts():
    data = load_full_results()
    assert len(data.circonscriptions_by_id) == 577
    assert len(data.districts) == 501
    assert sum(data.first_round_seats.values()) == 76
    assert all(
        list(d.competing_parties_results) == list(DESTINATIONS) for d in data.districts
    )
    assert all(
        list(d.eliminated_parties_results) == list(DESTINATIONS) for d in data.districts
    )


def test_second_round_loader_matches_simulated_districts():
    first_round = load_full_results()
    second_round = load_second_round_results()
    assert {d.circonscription.id for d in first_round.districts} <= set(second_round)
    assert all(result.exprimes <= result.inscrits for result in second_round.values())


class TestPreparedTable:
    """Invariants de la table produite par `scripts/prepare_data.py`.

    Le rapprochement avec les candidatures du 2nd tour se faisait par (nom,
    prénom) sans la circonscription. Deux homonymes se présentaient dans des
    circonscriptions différentes, et VALLON Jean-Paul (DVD, 0702), éliminé au
    1er tour, héritait de la qualification de son homonyme RN en 2601 : la
    circonscription était simulée en triangulaire au lieu d'un duel, et ses
    10 509 voix quittaient le réservoir des reports.
    """

    def test_aucun_candidat_au_second_tour_sans_qualification(self):
        first_round = load_full_results()
        for district in first_round.districts:
            competing = {
                party
                for party, votes in district.competing_parties_results.items()
                if votes > 0
            }
            eliminated = {
                party
                for party, votes in district.eliminated_parties_results.items()
                if votes > 0
            }
            assert competing, f"{district.circonscription.id} sans qualifié"
            assert len(competing) <= 4, (
                f"{district.circonscription.id} : {len(competing)} qualifiés, "
                "au-delà d'une quadrangulaire"
            )
            assert competing | eliminated, district.circonscription.id

    def test_la_circonscription_0702_est_un_duel(self):
        first_round = load_full_results()
        district = next(
            d for d in first_round.districts if d.circonscription.id == "0702"
        )
        assert district.n_competing() == 2
        assert district.eliminated_parties_results[PoliticalFamily.DVD] == 10_509
