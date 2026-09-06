"""
Le modèle ancré sur la participation du 1er tour.

L'essentiel porte sur deux garanties. D'abord que les deux croyances déclarées
(en points de participation) se traduisent bien en la bande annoncée : c'est tout
l'intérêt de l'élicitation, un lecteur doit pouvoir contester « ±5 points » et
savoir que le modèle fait vraiment ça. Ensuite que la rétention déduite respecte
exactement la comptabilité des voix — elle n'est plus tirée, donc plus rien ne la
borne à part cette identité.
"""

import numpy as np
import pytest
from scipy.special import expit, logit

from analyse_legislatives import models
from analyse_legislatives.data import load_full_results
from analyse_legislatives.config import (
    DEFAULT_FREE_TARGETS,
    DEFAULT_TRANSFER_ORDERINGS,
)
from analyse_legislatives.models.expressed_anchored import (
    Z90,
    KernelAnchoredModel,
)
from analyse_legislatives.parties import NON_EXPRIMES
from analyse_legislatives.transfers import TransferMatrix


@pytest.fixture(scope="module")
def districts():
    return load_full_results().districts


@pytest.fixture
def model():
    return models.build("kernel_anchored", seed=20240707)


class TestTheBeliefsMustBeDeclared:
    """
    `build()` fournit les trois croyances depuis `config/model.yaml`, où elles
    sont DÉCLARÉES et donc contestables. Le garde-fou porte sur le constructeur :
    personne ne doit pouvoir instancier ce modèle sans les avoir écrites quelque
    part.
    """

    @staticmethod
    def instantiate(**kwargs):
        return KernelAnchoredModel(
            transfer_orderings=DEFAULT_TRANSFER_ORDERINGS,
            non_expressed_tilt_bounds=(-1.0, 2.0),
            non_expressed_retention_prior=(8.0, 2.0),
            mixing_prior=(2.0, 2.0),
            dirichlet_alpha_bounds=(0.5, 1.0),
            qualified_demobilisation_prior=(2.0, 18.0),
            free_targets=DEFAULT_FREE_TARGETS,
            rng=np.random.default_rng(0),
            **kwargs,
        )

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"national_expressed_band_pts": 5},
            {"district_expressed_band_pts": 4},
            {"national_expressed_band_pts": 5, "district_expressed_band_pts": 4},
            {"national_expressed_band_pts": 5, "expected_expressed_change_pts": -2.40},
        ],
    )
    def test_refuses_to_run_without_all_three_statements(self, kwargs):
        """L'échelle d'un décalage entre deux tours n'est pas identifiable à partir
        d'un seul tour. Aucune valeur par défaut dans le code : une croyance
        assumée doit être écrite, pas héritée."""
        with pytest.raises(ValueError, match="must be declared"):
            self.instantiate(**kwargs)

    def test_accepts_all_three(self):
        self.instantiate(
            national_expressed_band_pts=6.58,
            district_expressed_band_pts=4.0,
            expected_expressed_change_pts=-2.40,
        )

    @pytest.mark.parametrize("pts", [0, -3, 50, 120])
    def test_rejects_band_half_widths_outside_a_plausible_range(self, pts):
        with pytest.raises(ValueError, match="Expressed-share bands"):
            self.instantiate(
                national_expressed_band_pts=pts,
                district_expressed_band_pts=4,
                expected_expressed_change_pts=-2.40,
            )

    def test_build_supplies_them_from_the_declared_config(self):
        """Le YAML est la source de vérité : `build()` n'invente rien, il lit."""
        from analyse_legislatives.config import (
            DEFAULT_DISTRICT_EXPRESSED_BAND_PTS,
            DEFAULT_EXPECTED_EXPRESSED_CHANGE_PTS,
            DEFAULT_NATIONAL_EXPRESSED_BAND_PTS,
        )

        model = models.build("kernel_anchored")
        assert (
            model.expected_expressed_change_pts == DEFAULT_EXPECTED_EXPRESSED_CHANGE_PTS
        )
        assert model.national_expressed_band_pts == DEFAULT_NATIONAL_EXPRESSED_BAND_PTS
        assert model.district_expressed_band_pts == DEFAULT_DISTRICT_EXPRESSED_BAND_PTS


class TestElicitationBecomesSigma:
    def test_the_band_lands_inside_the_declared_points_on_both_sides(self, model):
        """La logit n'étant pas symétrique, ±5 points ne valent pas le même
        écart-type en haut et en bas. On retient le côté le plus serré, donc la
        bande obtenue doit tenir DANS ±5 des deux côtés."""
        anchor, pts = 0.6512, 5.0
        sigma = model._sigma(pts, anchor)
        low = expit(logit(anchor) - Z90 * sigma)
        high = expit(logit(anchor) + Z90 * sigma)
        assert anchor - pts / 100 <= low
        assert high <= anchor + pts / 100

    def test_a_wider_belief_gives_a_wider_sigma(self, model):
        sigmas = [model._sigma(p, 0.6512) for p in (3, 4, 5, 6)]
        assert sigmas == sorted(sigmas)


class TestJointProjectionOfNonExpressedFlows:
    def test_qualified_parties_can_now_lose_voters(self, districts):
        """Le point de ce mécanisme : la ligne d'un parti qualifié n'est plus
        forcément l'identité. Mesuré sur 2024, 52 circonscriptions montrent un
        qualifié qui perd des voix entre les deux tours — ce que le modèle
        interdisait jusqu'ici."""
        from analyse_legislatives.models import NON_EXPRESSED_TILT_MIDPOINT
        from analyse_legislatives.transfers import normalize_for_district

        model = models.build(
            "kernel_anchored",
            seed=1,
            national_expressed_band_pts=8,
            district_expressed_band_pts=6,
            expected_expressed_change_pts=-6.0,
        )
        seen = False
        for _ in range(10):
            for matrix, d in zip(model.sample_transfer_matrices(districts), districts):
                normalized = normalize_for_district(
                    matrix, d, NON_EXPRESSED_TILT_MIDPOINT
                )
                for party, votes in d.competing_parties_results.items():
                    if votes > 0 and normalized.rates[party][NON_EXPRIMES] > 0:
                        seen = True
        assert seen

    def test_both_finalists_are_demobilised_at_the_same_rate(self, districts):
        """Rien ne dit lequel des deux finalistes démobilise le plus : un taux
        commun est l'hypothèse minimale. Elle ne rend pas le levier neutre pour
        autant — `rho` met à l'échelle la base du 1er tour mais pas les reports
        reçus."""
        model = models.build(
            "kernel_anchored",
            seed=3,
            national_expressed_band_pts=8,
            district_expressed_band_pts=6,
            expected_expressed_change_pts=-6.0,
        )
        for matrix, d in zip(model.sample_transfer_matrices(districts), districts):
            qualified = [p for p, v in d.competing_parties_results.items() if v > 0]
            rates = {matrix.own_retentions.get(p, 1.0) for p in qualified}
            assert len(rates) == 1

    def test_eliminated_rows_are_also_adjusted(self, districts):
        """L'ancre ne doit plus être dépensée uniquement sur les deux anciens
        leviers : les taux des familles éliminées vers NON_EXPRIMES participent à
        la même projection."""
        from analyse_legislatives.models import NON_EXPRESSED_TILT_MIDPOINT
        from analyse_legislatives.transfers import normalize_for_district

        model = models.build("national_anchored", seed=29)
        draw = model.draw_simulation()
        prior_rows = model._sample_rows_per_district(districts, draw)
        matrices = model._complete_matrices(prior_rows, districts, draw)

        changed = 0
        for rows, matrix, district in zip(prior_rows, matrices, districts):
            before = normalize_for_district(
                TransferMatrix(
                    {**rows, NON_EXPRIMES: {NON_EXPRIMES: draw.non_expressed_retention}}
                ),
                district,
                NON_EXPRESSED_TILT_MIDPOINT,
            )
            after = normalize_for_district(
                matrix, district, NON_EXPRESSED_TILT_MIDPOINT
            )
            for source, votes in district.eliminated_parties_results.items():
                if votes > 0 and district.competing_parties_results.get(source, 0) == 0:
                    changed += not np.isclose(
                        before.rates[source][NON_EXPRIMES],
                        after.rates[source][NON_EXPRIMES],
                    )
        assert changed > 0


class TestEveryVoteGoesThroughTheMatrix:
    """
    Les voix des partis qualifiés transitent par la matrice au lieu d'être
    ajoutées telles quelles au résultat. Sans ça, leur ligne est inatteignable et
    `rho` ne s'applique qu'aux éliminés de leur propre famille — 1,6 % des
    inscrits, bien trop peu pour réaliser la dérive déclarée. Le symptôme était
    silencieux : le modèle annonçait -4,34 points et en produisait -1,89.
    """

    def test_no_ballot_is_created_or_lost(self, districts):
        model = models.build("national_anchored", seed=11)
        for prediction, d in zip(
            model.predict_all_circonscriptions(districts), districts
        ):
            registered = (
                sum(d.competing_parties_results.values())
                + sum(d.eliminated_parties_results.values())
                + d.non_expressed
            )
            assert sum(prediction.results.values()) == registered

    def test_the_solved_target_is_reached_exactly(self, districts):
        """Test comptable, sans bruit multinomial : la part de suffrages exprimés
        qu'implique la matrice tirée doit être exactement la cible réalisable de
        la projection."""
        from analyse_legislatives.models import NON_EXPRESSED_TILT_MIDPOINT
        from analyse_legislatives.transfers import normalize_for_district

        model = models.build("national_anchored", seed=13)
        matrices = model.sample_transfer_matrices(districts)
        targets = model._drawn_expressed_targets
        assert targets is not None

        for matrix, d, target in zip(matrices, districts, targets):
            normalized = normalize_for_district(matrix, d, NON_EXPRESSED_TILT_MIDPOINT)
            _, registered = model._first_round_expressed_share(d)
            expressed = sum(
                pool
                * sum(
                    v for k, v in normalized.rates[source].items() if k != NON_EXPRIMES
                )
                for source, pool in d.available_vote_pools_by_party().items()
            )
            assert expressed / registered == pytest.approx(target, abs=1e-9)


class TestDrift:
    def test_a_negative_drift_lowers_the_projection(self, districts):
        """La dérive doit mordre même lorsque la démobilisation positive est tenue
        identique dans les deux expériences."""
        totals = sum(
            sum(d.competing_parties_results.values())
            + sum(d.eliminated_parties_results.values())
            + d.non_expressed
            for d in districts
        )

        def median_turnout(drift):
            model = models.build(
                "kernel_anchored",
                seed=20240707,
                national_expressed_band_pts=5,
                district_expressed_band_pts=4,
                expected_expressed_change_pts=drift,
            )
            return np.median(
                [
                    sum(
                        v
                        for p in model.predict_all_circonscriptions(districts)
                        for k, v in p.results.items()
                        if k != NON_EXPRIMES
                    )
                    / totals
                    for _ in range(25)
                ]
            )

        assert median_turnout(-2.40) < median_turnout(0.0)

    def test_the_drift_is_signed_but_the_bands_are_not(self):
        models.build(
            "kernel_anchored",
            national_expressed_band_pts=5,
            district_expressed_band_pts=4,
            expected_expressed_change_pts=-2.40,
        )
        with pytest.raises(ValueError, match="Expressed-share bands"):
            models.build(
                "kernel_anchored",
                national_expressed_band_pts=-5,
                district_expressed_band_pts=4,
                expected_expressed_change_pts=-2.40,
            )


class TestAnchoring:
    def test_every_district_gets_its_own_retention(self, model, districts):
        """La rétention peut varier localement, sauf lorsque la cible bute sur le
        plancher structurel documenté et que plusieurs districts saturent à 1."""
        for _ in range(10):
            matrices = model.sample_transfer_matrices(districts)
            retentions = {m.rates[NON_EXPRIMES][NON_EXPRIMES] for m in matrices}
            assert all(0 <= value <= 1 for value in retentions)
            if len(retentions) > 1:
                return
        pytest.fail("aucune variation locale hors saturation en dix simulations")

    def test_the_national_median_sits_at_the_anchor_plus_the_drift(
        self, model, districts
    ):
        """Le prior est centré sur la participation du 1er tour DÉCALÉE de la
        dérive déclarée — sans jamais consulter le 2nd tour. C'est une propriété du
        prior, pas une performance."""
        total = np.array(
            [
                sum(d.competing_parties_results.values())
                + sum(d.eliminated_parties_results.values())
                + d.non_expressed
                for d in districts
            ],
            float,
        )
        t1, _ = zip(*(model._first_round_expressed_share(d) for d in districts))
        anchor = float(total @ np.array(t1) / total.sum())

        turnouts = []
        for _ in range(40):
            preds = model.predict_all_circonscriptions(districts)
            voted = sum(
                v for p in preds for k, v in p.results.items() if k != NON_EXPRIMES
            )
            turnouts.append(voted / total.sum())
        expected = anchor + model.expected_expressed_change_pts / 100
        assert np.median(turnouts) == pytest.approx(expected, abs=0.04)


class TestTheAnchorIsOrthogonalToTheSpatialStructure:
    """
    L'ancrage est un mixin justement pour qu'on puisse le croiser avec les
    variantes de base : sans ça, le comparer à `national` changerait deux choses à
    la fois (le noyau ET l'ancrage) et aucun des deux effets ne serait lisible.
    """

    def test_anchoring_moves_turnout_the_same_way_on_both_bases(self, districts):
        """Le mixin doit produire le même DÉPLACEMENT de participation quelle que
        soit la variante en dessous, sinon l'effet mesuré ne serait pas le sien."""
        totals = sum(
            sum(d.competing_parties_results.values())
            + sum(d.eliminated_parties_results.values())
            + d.non_expressed
            for d in districts
        )

        # 150 tirages, pas 20 : la dérive nationale a une bande de +/-10 points,
        # donc la médiane sur 20 tirages porte plus de bruit Monte-Carlo que l'effet
        # mesuré ici et le test devient un tirage au sort.
        def median_turnout(name):
            model = models.build(name, seed=20240707)
            return np.median(
                [
                    sum(
                        v
                        for p in model.predict_all_circonscriptions(districts)
                        for k, v in p.results.items()
                        if k != NON_EXPRIMES
                    )
                    / totals
                    for _ in range(150)
                ]
            )

        first_round = (
            sum(
                sum(d.competing_parties_results.values())
                + sum(d.eliminated_parties_results.values())
                for d in districts
            )
            / totals
        )
        anchored = [
            median_turnout("national_anchored"),
            median_turnout("kernel_anchored"),
        ]
        plain_national = median_turnout("national")

        # Les deux variantes ancrées doivent s'accorder : c'est l'objet de la
        # classe — l'effet de l'ancre ne dépend pas de la structure spatiale.
        assert abs(anchored[0] - anchored[1]) < 0.02

        # Et l'ancre doit tenir son nom : la dérive déclarée étant nulle, elle
        # ramène la participation vers celle du 1er tour, plus près que ne le fait
        # la variante libre, dont la rétention des non-exprimés flotte dans son
        # prior.
        assert max(abs(a - first_round) for a in anchored) < abs(
            plain_national - first_round
        )
