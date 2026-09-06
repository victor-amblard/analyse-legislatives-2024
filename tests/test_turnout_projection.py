import numpy as np
import pytest
from scipy.special import logit

from analyse_legislatives.models.turnout_projection import (
    ordinal_bounds_from_order_constraint,
    project_probabilities,
    project_probabilities_batch,
    restricted_non_expressed_probability,
    set_restricted_non_expressed_probability,
)
from analyse_legislatives.parties import NON_EXPRIMES, PoliticalFamily


def test_projection_reaches_the_weighted_target_with_one_common_logit_shift():
    prior = np.array([0.80, 0.05, 0.20])
    weights = np.array([0.30, 0.45, 0.25])
    projected = project_probabilities(prior, weights, 0.31, np.zeros(3), np.ones(3))

    assert weights @ projected == pytest.approx(0.31)
    shifts = logit(projected) - logit(prior)
    assert shifts == pytest.approx(np.repeat(shifts[0], 3))


def test_projection_respects_an_active_ordinal_bound():
    projected = project_probabilities(
        [0.2, 0.2], [0.5, 0.5], 0.5, [0.0, 0.0], [0.3, 1.0]
    )
    assert projected[0] == pytest.approx(0.3)
    assert projected[1] == pytest.approx(0.7)


def test_row_tilt_preserves_other_ratios_and_hits_the_local_probability():
    row = {
        PoliticalFamily.ENSx: 0.5,
        PoliticalFamily.RNx: 0.3,
        NON_EXPRIMES: 0.2,
    }
    available = {PoliticalFamily.ENSx, NON_EXPRIMES}
    adjusted = set_restricted_non_expressed_probability(row, available, 0.4)

    assert sum(adjusted.values()) == pytest.approx(1.0)
    assert adjusted[PoliticalFamily.ENSx] / adjusted[
        PoliticalFamily.RNx
    ] == pytest.approx(row[PoliticalFamily.ENSx] / row[PoliticalFamily.RNx])
    assert restricted_non_expressed_probability(adjusted, available) == pytest.approx(
        0.4
    )


def test_ordinal_upper_bound_keeps_a_strictly_preferred_target_above_non_expressed():
    row = {
        PoliticalFamily.ENSx: 0.5,
        PoliticalFamily.RNx: 0.3,
        NON_EXPRIMES: 0.2,
    }
    tiers = [[PoliticalFamily.ENSx], [PoliticalFamily.RNx, NON_EXPRIMES]]
    available = {PoliticalFamily.ENSx, PoliticalFamily.RNx, NON_EXPRIMES}
    _, upper = ordinal_bounds_from_order_constraint(row, tiers, available)
    adjusted = set_restricted_non_expressed_probability(row, available, upper)

    assert adjusted[NON_EXPRIMES] == pytest.approx(adjusted[PoliticalFamily.ENSx])
    assert adjusted[NON_EXPRIMES] > adjusted[PoliticalFamily.RNx]


class TestBatchedProjection:
    """`project_probabilities` sert d'oracle au solveur groupé.

    La version scalaire n'est plus appelée en production : le simulateur résout
    les 501 circonscriptions ensemble, la recherche de racine par
    circonscription ayant dominé son temps d'exécution. Elle reste ici comme
    référence lisible — une seule circonscription, un `brentq` — contre laquelle
    la bissection vectorisée est vérifiée.
    """

    def test_matches_the_scalar_solver_on_random_districts(self):
        rng = np.random.default_rng(11)
        width = 8
        drawn = np.full((60, width), 0.5)
        votes = np.zeros((60, width))
        lowest = np.zeros((60, width))
        highest = np.ones((60, width))
        targets = np.empty(60)
        expected = []

        for row in range(60):
            span = int(rng.integers(4, width + 1))
            low = rng.uniform(0, 0.3, span)
            high = low + rng.uniform(0.05, 0.7, span)
            rates = low + rng.uniform(0, 1, span) * (high - low)
            weights = rng.uniform(1.0, 5e4, span)
            # Une cible strictement intérieure : aux bornes, les deux solveurs
            # renvoient la borne sans chercher de racine, ce qui ne teste rien.
            floor, ceiling = float(weights @ low), float(weights @ high)
            targets[row] = floor + 0.5 * (ceiling - floor)

            drawn[row, :span] = rates
            votes[row, :span] = weights
            lowest[row, :span] = low
            highest[row, :span] = high
            expected.append(
                project_probabilities(rates, weights, targets[row], low, high)
            )

        projected = project_probabilities_batch(
            drawn, votes, targets, lowest, highest
        )
        for row, reference in enumerate(expected):
            assert projected[row, : reference.size] == pytest.approx(
                reference, abs=1e-12
            )

    def test_frozen_reservoirs_stay_at_their_bound(self):
        """Un taux tiré à 0 ou à 1 ne bouge pas : le décalage n'a pas de prise.

        Le solveur groupé n'a pas de masque pour ce cas — il s'appuie sur
        `logit(0) = -inf` et `logit(1) = +inf`, que `expit` ramène exactement à
        0 et 1. C'est ce raccourci que ce test protège.
        """
        projected = project_probabilities_batch(
            np.array([[0.0, 1.0, 0.5]]),
            np.array([[100.0, 100.0, 100.0]]),
            np.array([150.0]),
            np.zeros((1, 3)),
            np.ones((1, 3)),
        )
        assert projected[0, 0] == 0.0
        assert projected[0, 1] == 1.0
        assert projected[0, 2] == pytest.approx(0.5)

    def test_padding_columns_do_not_move_the_solution(self):
        """Les colonnes de remplissage portent `votes = 0` : elles doivent être
        strictement sans effet, sinon les circonscriptions à peu de réservoirs
        seraient projetées différemment des autres."""
        rates = np.array([0.8, 0.05, 0.2])
        weights = np.array([300.0, 450.0, 250.0])
        target = np.array([310.0])
        tight = project_probabilities_batch(
            rates[None, :], weights[None, :], target, np.zeros((1, 3)), np.ones((1, 3))
        )
        padded = project_probabilities_batch(
            np.append(rates, [0.5, 0.5])[None, :],
            np.append(weights, [0.0, 0.0])[None, :],
            target,
            np.zeros((1, 5)),
            np.ones((1, 5)),
        )
        assert padded[0, :3] == pytest.approx(tight[0], abs=1e-15)
