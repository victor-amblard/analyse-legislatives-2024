"""Règle de référence « tête au premier tour », qui ne modélise aucun report."""

import numpy as np

from analyse_legislatives.baselines import (
    NO_WINNER,
    first_round_leader_seats,
    first_round_leader_winners,
)
from analyse_legislatives.parties import FAMILIES, PoliticalFamily

from conftest import make_district

NFP = FAMILIES.index(PoliticalFamily.NFPx)
RN = FAMILIES.index(PoliticalFamily.RNx)
ENS = FAMILIES.index(PoliticalFamily.ENSx)


class TestWinners:
    def test_leader_among_qualified_wins(self, duel):
        assert first_round_leader_winners([duel]).tolist() == [NFP]

    def test_eliminated_party_never_wins(self):
        """Le réservoir ENS+ est le plus gros de la circonscription, mais son
        candidat n'est pas au second tour : il ne peut pas être désigné."""
        district = make_district(
            competing={PoliticalFamily.NFPx: 10_000, PoliticalFamily.RNx: 9_000},
            eliminated={PoliticalFamily.ENSx: 20_000},
        )
        assert first_round_leader_winners([district]).tolist() == [NFP]

    def test_same_family_eliminated_votes_do_not_count(self):
        """Un second candidat de la même famille appartient au réservoir de
        reports : la règle de référence l'ignore, sans quoi elle modéliserait un
        report implicite."""
        district = make_district(
            competing={PoliticalFamily.NFPx: 10_000, PoliticalFamily.RNx: 9_000},
            eliminated={PoliticalFamily.RNx: 5_000},
        )
        assert first_round_leader_winners([district]).tolist() == [NFP]

    def test_triangulaire_takes_the_first_of_three(self, triangulaire):
        assert first_round_leader_winners([triangulaire]).tolist() == [NFP]

    def test_district_without_qualified_candidate(self):
        district = make_district(competing={}, eliminated={PoliticalFamily.NFPx: 10})
        assert first_round_leader_winners([district]).tolist() == [NO_WINNER]


class TestSeats:
    def test_one_seat_per_district(self, districts):
        seats = first_round_leader_seats(districts)
        assert seats.sum() == len(districts)
        assert seats[NFP] == 2

    def test_first_round_seats_are_added(self, districts):
        seats = first_round_leader_seats(districts, {"RN+": 39, "ENS+": 2})
        assert seats.sum() == len(districts) + 41
        assert seats[RN] == 39
        assert seats[ENS] == 2

    def test_seats_follow_the_canonical_family_order(self):
        district = make_district(
            competing={PoliticalFamily.RNx: 10_000, PoliticalFamily.NFPx: 9_000}
        )
        expected = np.zeros(len(FAMILIES))
        expected[RN] = 1
        assert first_round_leader_seats([district]).tolist() == expected.tolist()
