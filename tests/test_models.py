"""
Propriétés attendues de toutes les variantes du modèle.

Écrits en paramétrant sur le registre `MODELS` plutôt que sur une classe :
une nouvelle variante hérite automatiquement de ces garanties, et un modèle qui
les violerait échoue dès son ajout.
"""

from dataclasses import replace

import numpy as np
import pytest

from analyse_legislatives import simulation
from analyse_legislatives.config import DEFAULT_NON_EXPRESSED_RETENTION_PRIOR
from analyse_legislatives.config import (
    DEFAULT_FREE_TARGETS,
    DEFAULT_TRANSFER_ORDERINGS,
)
from analyse_legislatives.models import MODELS, STOCHASTIC_MODELS, build
from conftest import make_district
from analyse_legislatives.parties import (
    NON_EXPRIMES,
    DESTINATIONS,
    FAMILIES,
    PoliticalFamily,
)

ALL_MODELS = list(STOCHASTIC_MODELS)

_EXPRESSED_SHARE_BELIEFS = {
    "national_expressed_band_pts": 5,
    "district_expressed_band_pts": 4,
    "expected_expressed_change_pts": -2.40,
}


def direct_kernel_model(**kwargs):
    """Construct the class directly when testing constructor validation."""
    defaults = {
        "non_expressed_tilt_bounds": (-1.0, 2.0),
        "non_expressed_retention_prior": (8.0, 2.0),
        "qualified_demobilisation_prior": (2.0, 18.0),
        "mixing_prior": (2.0, 2.0),
        "dirichlet_alpha_bounds": (0.5, 1.0),
        "free_targets": (),
    }
    return MODELS["kernel_anchored"](**(defaults | _EXPRESSED_SHARE_BELIEFS | kwargs))


REQUIRED_ARGS = {
    "national_anchored": _EXPRESSED_SHARE_BELIEFS,
    "kernel_anchored": _EXPRESSED_SHARE_BELIEFS,
}
"""Croyances que certains modèles exigent explicitement (voir
`KernelAnchoredModel`). Les tests génériques les fournissent pour pouvoir
continuer à balayer TOUTES les variantes : ce sont des arguments obligatoires,
pas des valeurs par défaut cachées."""


def build_for_test(name, **kwargs):
    return build(name, **(REQUIRED_ARGS.get(name, {}) | kwargs))


@pytest.mark.parametrize("name", ALL_MODELS)
class TestEveryModel:
    def test_conserves_registered_voters(self, name, districts):
        """Un report déplace des voix, il n'en crée ni n'en détruit : le total
        par circonscription doit rester celui du 1er tour."""
        cube = simulation.run(build_for_test(name, seed=0), districts, 3)
        expected = [
            sum(d.competing_parties_results.values())
            + sum(d.eliminated_parties_results.values())
            + d.non_expressed
            for d in districts
        ]
        assert cube.sum(axis=2).tolist() == [expected] * 3

    def test_is_reproducible_at_fixed_seed(self, name, districts):
        first = simulation.run(build_for_test(name, seed=7), districts, 3)
        second = simulation.run(build_for_test(name, seed=7), districts, 3)
        assert np.array_equal(first, second)

    def test_eliminated_parties_receive_nothing(self, name, districts):
        """Un parti non qualifié doit finir à zéro partout : sinon des voix sont
        attribuées à un candidat qui n'est pas sur le bulletin."""
        cube = simulation.run(build_for_test(name, seed=0), districts, 3)
        for j, district in enumerate(districts):
            for k, destination in enumerate(DESTINATIONS):
                if (
                    destination in FAMILIES
                    and district.competing_parties_results[destination] == 0
                ):
                    assert (cube[:, j, k] == 0).all(), f"{destination} en {j}"


@pytest.mark.parametrize("name", ALL_MODELS)
def test_ordinal_mode_respects_the_declared_ordering(name, districts):
    """
    Le mode ordinal ne promet qu'une chose : l'ordre de préférence déclaré est
    respecté. On le vérifie sur la ligne ENS+, dont l'ordre place RN+ en dernier,
    dans un duel NFP+/RN+ : le report ENS+ -> NFP+ doit dominer ENS+ -> RN+.
    """
    from analyse_legislatives.transfers import normalize_for_district

    model = build_for_test(name, seed=3)
    duel = districts[0]
    for _ in range(20):
        parameters = model.sample_transfer_matrices([duel])[0]
        normalized = normalize_for_district(parameters, duel, 0.5)
        row = normalized.rates[PoliticalFamily.ENSx]
        assert row[PoliticalFamily.NFPx] >= row[PoliticalFamily.RNx]


def test_unknown_model_name_is_rejected():
    with pytest.raises(ValueError, match="Modèle inconnu"):
        build("inexistant")


def test_orderings_are_mandatory():
    """Les ordres de préférence sont le contenu du modèle : sans eux il n'y a rien
    à tirer. Construire à la main ne doit pas contourner la validation."""
    with pytest.raises(ValueError, match="transfer_orderings"):
        direct_kernel_model(transfer_orderings={})


def test_empty_ordering_is_rejected():
    with pytest.raises(ValueError, match="vides"):
        direct_kernel_model(transfer_orderings={PoliticalFamily.ENSx: []})


def test_predict_one_district_requires_explicit_parameters(districts):
    """Une variante stochastique doit tirer ses matrices conjointement."""
    model = build_for_test("kernel_anchored", seed=0)
    with pytest.raises(ValueError, match="exige `parameters`"):
        model.predict_circonscription(districts[0])


def test_national_model_shares_one_matrix_across_districts(districts):
    """Propriété qui définit la variante : aucune variation locale."""
    model = build("national", seed=0)
    matrices = model.sample_transfer_matrices(districts)
    assert matrices[0].to_matrix() == pytest.approx(matrices[1].to_matrix())


class TestKernelEdgeCases:
    def test_single_district_is_supported(self, duel):
        cube = simulation.run(build_for_test("kernel_anchored", seed=0), [duel], 2)
        assert cube.shape == (2, 1, len(DESTINATIONS))

    def test_identical_districts_are_supported(self, duel):
        cube = simulation.run(
            build_for_test("kernel_anchored", seed=0), [duel, duel], 2
        )
        assert cube.shape == (2, 2, len(DESTINATIONS))


class TestNestedDepartmentRegionKernel:
    """Le noyau départemental est EMBOÎTÉ : `rho_departement` à l'intérieur d'un
    département, `rho_region` (plafonné par `rho_departement`) entre départements
    d'une même région, 0 au-delà. Voir `first_round_variogram.py` pour la mesure
    qui justifie ces trois paliers."""

    @staticmethod
    def _nested_districts():
        """01 et 03 sont deux départements d'Auvergne-Rhône-Alpes ; 75
        (Île-de-France) est dans une autre région. Deux circonscriptions du 01
        pour tester le palier départemental lui-même."""
        return [
            make_district(competing={PoliticalFamily.NFPx: 1}, id="0101"),
            make_district(competing={PoliticalFamily.NFPx: 1}, id="0102"),
            make_district(competing={PoliticalFamily.NFPx: 1}, id="0301"),
            make_district(competing={PoliticalFamily.NFPx: 1}, id="7501"),
        ]

    def test_marginal_variance_is_invariant_to_rho(self):
        model = build_for_test(
            "kernel_anchored",
            seed=0,
            department_correlation=0.7,
            region_correlation=0.3,
        )
        draws = np.array(
            [model._local_latent_field(self._nested_districts()) for _ in range(4000)]
        )
        assert draws.var(axis=0) == pytest.approx(1.0, abs=0.1)

    def test_correlation_matches_each_tier(self):
        model = build_for_test(
            "kernel_anchored",
            seed=0,
            department_correlation=0.7,
            region_correlation=0.3,
        )
        draws = np.array(
            [model._local_latent_field(self._nested_districts()) for _ in range(4000)]
        )
        corr = np.corrcoef(draws.T)
        assert corr[0, 1] == pytest.approx(0.7, abs=0.05)  # même département
        assert corr[0, 2] == pytest.approx(0.3, abs=0.05)  # même région, dept ≠
        assert corr[0, 3] == pytest.approx(0.0, abs=0.05)  # régions différentes

    def test_kernel_matrix_matches_sampled_field(self):
        model = build_for_test(
            "kernel_anchored",
            seed=0,
            department_correlation=0.7,
            region_correlation=0.3,
        )
        K = model.kernel_matrix_for(self._nested_districts())
        assert K.diagonal() == pytest.approx(1.0)
        assert K[0, 1] == pytest.approx(0.7)
        assert K[0, 2] == pytest.approx(0.3)
        assert K[0, 3] == pytest.approx(0.0)

    def test_region_correlation_is_capped_by_department_correlation(self):
        """Une région ne peut pas être plus corrélée que le département qui la
        compose : le tirage brut est ramené à son plafond."""
        model = build_for_test(
            "kernel_anchored",
            seed=0,
            department_correlation=0.3,
            region_correlation=0.9,
        )
        assert model.region_correlation_for(0.3) == pytest.approx(0.3)

    def test_unmapped_department_keeps_department_level_correlation(self):
        """Un territoire ultramarin non couvert conserve son palier local."""
        model = build_for_test(
            "kernel_anchored",
            seed=0,
            department_correlation=0.7,
            region_correlation=0.9,  # au-dessus : vérifie l'absence de fuite
        )
        districts = [
            make_district(competing={PoliticalFamily.NFPx: 1}, id="98801"),
            make_district(competing={PoliticalFamily.NFPx: 1}, id="98802"),
        ]
        K = model.kernel_matrix_for(districts)
        assert K[0, 1] == pytest.approx(0.7)

    def test_french_abroad_districts_are_locally_independent(self):
        """`ZZ` est une catégorie administrative, pas un département commun."""
        model = build_for_test(
            "kernel_anchored",
            seed=0,
            department_correlation=0.7,
            region_correlation=0.5,
        )
        districts = [
            make_district(competing={PoliticalFamily.NFPx: 1}, id="ZZ01"),
            make_district(competing={PoliticalFamily.NFPx: 1}, id="ZZ11"),
        ]
        K = model.kernel_matrix_for(districts)
        assert K[0, 1] == pytest.approx(0.0)

    def test_unmapped_departments_never_share_a_region(self):
        """Deux départements non couverts DIFFÉRENTS (Français de l'étranger et
        outre-mer, par exemple) ne doivent jamais se retrouver dans la même
        région de repli : chaque département non couvert reste isolé."""
        model = build_for_test(
            "kernel_anchored",
            seed=0,
            department_correlation=0.7,
            region_correlation=0.5,
        )
        districts = [
            make_district(competing={PoliticalFamily.NFPx: 1}, id="ZZ01"),
            make_district(competing={PoliticalFamily.NFPx: 1}, id="ZX01"),
        ]
        K = model.kernel_matrix_for(districts)
        assert K[0, 1] == pytest.approx(0.0)


def test_kernel_model_varies_across_districts(districts):
    model = build_for_test("kernel_anchored", seed=0)
    matrices = model.sample_transfer_matrices(districts)
    assert matrices[0].to_matrix() != pytest.approx(matrices[1].to_matrix())


class TestKernelNationalLocalMixture:
    """Le kernel mélange réellement un facteur national et un champ local."""

    @staticmethod
    def transfer_rows(matrix):
        """Répartition entre candidats, conditionnellement à un vote exprimé.

        L'ancre modifie désormais toutes les colonnes NON_EXPRIMES, même lorsque
        la matrice politique sous-jacente est entièrement nationale.
        """
        rows = np.asarray(matrix.to_matrix())[:-1, :-1]
        totals = rows.sum(axis=1, keepdims=True)
        return np.divide(rows, totals, out=np.zeros_like(rows), where=totals > 0)

    @staticmethod
    def draw_with_weight(model, weight):
        """Rejoue un tirage en imposant lambda, sans toucher au reste."""
        return replace(model.draw_simulation(), mixing_weight=weight)

    def test_full_national_weight_shares_transfer_matrix(self, districts):
        model = build_for_test("kernel_anchored", seed=0)
        draw = self.draw_with_weight(model, 1.0)
        matrices = model.sample_transfer_matrices(districts, draw)
        reference = self.transfer_rows(matrices[0])
        for matrix in matrices[1:]:
            assert self.transfer_rows(matrix) == pytest.approx(reference)

    def test_zero_national_weight_keeps_local_variation(self, districts):
        model = build_for_test("kernel_anchored", seed=0)
        draw = self.draw_with_weight(model, 0.0)
        matrices = model.sample_transfer_matrices(districts, draw)
        assert not np.allclose(
            self.transfer_rows(matrices[0]), self.transfer_rows(matrices[1])
        )

    def test_fixed_mixing_weight_is_used(self, districts):
        """L'override fixe l'emporte sur le lambda du tirage : on en met un
        absurde dans le tirage, il ne doit avoir aucun effet."""
        model = build_for_test("kernel_anchored", seed=0, mixing_weight=1.0)
        draw = self.draw_with_weight(model, 0.0)
        matrices = model.sample_transfer_matrices(districts, draw)
        reference = self.transfer_rows(matrices[0])
        for matrix in matrices[1:]:
            assert self.transfer_rows(matrix) == pytest.approx(reference)

    @pytest.mark.parametrize("weight", [-0.01, 1.01])
    def test_fixed_mixing_weight_must_be_a_probability(self, weight):
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            build_for_test("kernel_anchored", mixing_weight=weight)


def test_unnormalized_row_is_refused(districts, matrix):
    """Garde-fou explicite : `np.random.Generator.multinomial` verserait
    silencieusement le reliquat dans la dernière colonne (l'abstention)."""
    from analyse_legislatives.transfers import TransferMatrix

    broken = TransferMatrix(
        {source: dict.fromkeys(row, 0.0) for source, row in matrix.rates.items()}
    )
    model = build("national", seed=0)
    with pytest.raises(ValueError, match="non normalisée"):
        model.predict_circonscription(districts[0], parameters=broken)


class TestAbstentionRetention:
    """
    La rétention de l'abstention est le seul « niveau » du modèle : elle n'a pas de
    destinations concurrentes à ordonner, donc l'approche ordinale ne s'y applique
    pas. Elle est tirée d'une loi Beta partagée par toutes les circonscriptions,
    sauf pour la variante qui la fait en plus varier par circonscription en
    fonction de l'abstention du 1er tour.
    """

    NATIONAL_RETENTION_MODELS = ["national"]
    """Les variantes ancrées partent aussi du prior Beta, puis projettent cette
    rétention avec les autres flux vers leur participation cible. Seul
    `national` conserve directement le tirage sans projection."""

    def retentions(self, model, districts, n=200):
        return [
            [
                m.rates[NON_EXPRIMES][NON_EXPRIMES]
                for m in model.sample_transfer_matrices(districts)
            ]
            for _ in range(n)
        ]

    @pytest.mark.parametrize("name", NATIONAL_RETENTION_MODELS)
    def test_stays_a_probability(self, name, districts):
        model = build_for_test(name, seed=0)
        values = np.array(self.retentions(model, districts))
        assert (values > 0).all() and (values < 1).all()

    @pytest.mark.parametrize("name", NATIONAL_RETENTION_MODELS)
    def test_shared_across_districts_within_a_simulation(self, name, districts):
        """C'est un comportement national, pas un bruit local : toutes les
        circonscriptions d'une même simulation partagent la même rétention."""
        model = build_for_test(name, seed=0)
        for row in self.retentions(model, districts, n=50):
            assert len(set(row)) == 1

    @pytest.mark.parametrize("name", NATIONAL_RETENTION_MODELS)
    def test_varies_between_simulations(self, name, districts):
        """Le point de la manœuvre : la rétention avait auparavant une valeur fixe,
        donc aucune incertitude propre."""
        model = build_for_test(name, seed=0)
        first_column = [row[0] for row in self.retentions(model, districts)]
        assert len(set(first_column)) > 100

    @pytest.mark.parametrize("name", NATIONAL_RETENTION_MODELS)
    def test_centred_on_the_prior_mean(self, name, districts):
        """
        Les tirages suivent bien la Beta déclarée : moyenne et écart-type, à 0.02
        près sur 2000 tirages.

        Les valeurs attendues sont DÉRIVÉES de `DEFAULT_NON_EXPRESSED_RETENTION_PRIOR` et non
        écrites en dur : ce test vérifie que le tirage honore le prior, pas que le
        prior vaut telle valeur. Les coder en dur le faisait échouer au premier
        changement de prior, en signalant une régression là où il n'y avait qu'un
        choix de modélisation.
        """
        a, b = DEFAULT_NON_EXPRESSED_RETENTION_PRIOR
        expected_mean = a / (a + b)
        expected_std = np.sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))

        model = build_for_test(name, seed=0)
        values = np.array([row[0] for row in self.retentions(model, districts, n=2000)])
        assert values.mean() == pytest.approx(expected_mean, abs=0.02)
        assert values.std() == pytest.approx(expected_std, abs=0.02)

    def test_custom_prior_is_honoured(self, districts):
        """Une Beta très concentrée doit coller à sa moyenne — ici 0.6."""
        model = build("national", seed=0, non_expressed_retention_prior=(600.0, 400.0))
        values = np.array(self.retentions(model, districts))
        assert values.mean() == pytest.approx(0.6, abs=0.01)

    def test_invalid_prior_is_rejected(self):
        with pytest.raises(ValueError, match="non_expressed_retention_prior"):
            build("national", non_expressed_retention_prior=(0.0, 2.0))
        with pytest.raises(ValueError, match="non_expressed_retention_prior"):
            build("national", non_expressed_retention_prior=(8.0, -1.0))


class TestFreeAbstentionTarget:
    """
    L'abstention est classée EN DERNIER dans chaque ligne ; DIV reste la seule
    destination libre, dont le rang n'est pas contraint.
    """

    @pytest.mark.parametrize("name", ALL_MODELS)
    def test_rows_still_sum_to_one(self, name, districts):
        """La part libre est prise sur la même normalisation : la ligne somme
        toujours à 1, sans quoi le tirage multinomial serait refusé."""
        model = build_for_test(name, seed=0)
        for _ in range(30):
            for m in model.sample_transfer_matrices(districts):
                for source in model.transfer_orderings:
                    assert sum(m.rates[source].values()) == pytest.approx(1.0)

    @pytest.mark.parametrize("name", ALL_MODELS)
    def test_party_order_still_holds(self, name, districts):
        """Retirer NON_EXPRIMES des ordres ne doit rien relâcher entre partis."""
        model = build_for_test(name, seed=0)
        for _ in range(30):
            for m in model.sample_transfer_matrices(districts):
                for source, tiers in model.transfer_orderings.items():
                    levels = [[m.rates[source][t] for t in tier] for tier in tiers]
                    for i in range(len(levels) - 1):
                        assert min(levels[i]) >= max(levels[i + 1]) - 1e-9

    @pytest.mark.parametrize("name", ALL_MODELS)
    def test_abstention_never_beats_a_strictly_preferred_party(self, name, districts):
        """NON_EXPRIMES est dans le dernier palier : sa part ne peut jamais dépasser celle
        d'une destination d'un palier STRICTEMENT supérieur — mais elle peut dépasser
        celle de ses ex aequo (le parti le moins préféré)."""
        model = build_for_test(name, seed=0)
        for _ in range(40):
            for m in model.sample_transfer_matrices(districts):
                for source, tiers in model.transfer_orderings.items():
                    row = m.rates[source]
                    higher = [row[t] for tier in tiers[:-1] for t in tier if t in row]
                    if higher:
                        assert row[NON_EXPRIMES] <= min(higher) + 1e-9, (
                            f"ligne {source}"
                        )

    def test_abstention_may_exceed_its_tied_party(self, districts):
        """Le point de la manœuvre : NON_EXPRIMES n'étant plus SEULE au dernier palier, elle
        doit pouvoir dépasser le parti avec lequel elle est ex aequo — ce qu'un palier
        `[NON_EXPRIMES]` isolé interdisait."""
        model = build_for_test("kernel_anchored", seed=0)
        seen = False
        for _ in range(200):
            row = model.sample_transfer_matrices(districts)[0].rates[
                PoliticalFamily.ENSx
            ]
            if row[NON_EXPRIMES] > row[PoliticalFamily.RNx]:
                seen = True
                break
        assert seen, (
            "NON_EXPRIMES doit pouvoir dépasser RN+, son ex aequo de dernier palier"
        )

    def test_abstention_stays_under_the_strictly_preferred_tier_in_a_duel(self, duel):
        """Conséquence mécanique dans un duel NFP+/RN+ sur la ligne ENS+ : NFP+ est
        d'un palier strictement supérieur, donc NON_EXPRIMES reste sous NFP+ — ce qui la borne
        à 1/2 de la ligne (et non 1/3, comme lorsque RN+ la dominait aussi)."""
        from analyse_legislatives.transfers import normalize_for_district

        model = build_for_test("kernel_anchored", seed=0)
        for _ in range(50):
            parameters = model.sample_transfer_matrices([duel])[0]
            row = normalize_for_district(parameters, duel, 0.5).rates[
                PoliticalFamily.ENSx
            ]
            assert row[NON_EXPRIMES] <= row[PoliticalFamily.NFPx] + 1e-9
            assert row[NON_EXPRIMES] <= 0.5 + 1e-9

    def test_free_target_may_not_also_be_ordered(self):
        """Garde-fou : une destination à la fois ordonnée et libre serait comptée
        deux fois dans la ligne."""
        with pytest.raises(ValueError, match="ordonnées et libres"):
            direct_kernel_model(
                transfer_orderings={
                    PoliticalFamily.ENSx: [[PoliticalFamily.LR, PoliticalFamily.DIV]]
                },
                free_targets=(PoliticalFamily.DIV,),
            )


def test_default_draws_one_national_alpha_per_simulation(districts):
    model = build("national", seed=0)
    first = model.draw_simulation().alpha
    second = model.draw_simulation().alpha
    assert 0.5 <= first <= 1.0
    assert 0.5 <= second <= 1.0
    assert first != second


def test_sensitivity_may_override_demobilisation_explicitly():
    model = build("national", seed=0, qualified_demobilisation=0.15)
    assert model.draw_simulation().qualified_demobilisation == 0.15


@pytest.mark.parametrize("value", [-0.01, 1.0, 1.2])
def test_fixed_demobilisation_must_be_a_probability(value):
    with pytest.raises(ValueError, match="qualified_demobilisation"):
        build("national", qualified_demobilisation=value)


def test_dirichlet_concentration_must_be_positive():
    with pytest.raises(ValueError, match="strictement positive"):
        build("national", dirichlet_concentration=0)


@pytest.mark.parametrize("name", ALL_MODELS)
def test_qualified_demobilisation_is_positive_and_common_within_district(
    name, districts
):
    model = build_for_test(name, seed=0)
    draw = model.draw_simulation()
    matrices = model.sample_transfer_matrices(districts, draw)
    baseline = draw.qualified_demobilisation
    assert 0 < baseline < 1
    for matrix in matrices:
        rates = {1 - retention for retention in matrix.own_retentions.values()}
        assert len(rates) == 1
        rate = rates.pop()
        assert 0 <= rate <= 1
        if name == "national":
            assert rate == pytest.approx(baseline)


@pytest.mark.parametrize("prior", [(0.0, 2.0), (2.0, 0.0), (-1.0, 2.0)])
def test_qualified_demobilisation_prior_must_be_positive(prior):
    with pytest.raises(ValueError, match="qualified_demobilisation_prior"):
        build("national", qualified_demobilisation_prior=prior)


@pytest.mark.parametrize("bounds", [(0.0, 1.0), (1.0, 0.5), (1.0, 1.0)])
def test_dirichlet_alpha_bounds_must_be_positive_and_increasing(bounds):
    with pytest.raises(ValueError, match="strictement positives et croissantes"):
        build("national", dirichlet_alpha_bounds=bounds)


class TestFreeDivDestination:
    """DIV est libre en DESTINATION (aucun rang déclaré) tout en restant une SOURCE
    à part entière. C'est le cas limite du mécanisme `free_targets`."""

    def test_div_never_transfers_to_itself(self, districts):
        """Une destination libre qui est aussi la source doit être retirée de cette
        ligne — sinon la ligne compte une part DIV->DIV que `to_matrix` remet à
        zéro, et elle ne somme plus à 1."""
        model = build_for_test("kernel_anchored", seed=0)
        assert PoliticalFamily.DIV not in model.free_targets_for(PoliticalFamily.DIV)
        for m in model.sample_transfer_matrices(districts):
            assert PoliticalFamily.DIV not in m.rates[PoliticalFamily.DIV]
            assert sum(m.rates[PoliticalFamily.DIV].values()) == pytest.approx(1.0)

    def test_div_reaches_every_rank_as_a_destination(self, districts):
        """Comme NON_EXPRIMES : sa part doit pouvoir se placer n'importe où dans la ligne."""
        model = build_for_test("kernel_anchored", seed=0)
        ranks, width = set(), None
        for _ in range(600):
            row = model.sample_transfer_matrices(districts)[0].rates[
                PoliticalFamily.NFPx
            ]
            width = len(row)
            ranks.add(sorted(row, key=lambda t: -row[t]).index(PoliticalFamily.DIV) + 1)
        assert ranks == set(range(1, width + 1))

    def test_incomplete_row_is_rejected(self):
        """Une destination oubliée des deux côtés ne recevrait jamais de report,
        silencieusement : la construction doit échouer."""
        incomplete = {
            PoliticalFamily.ENSx: [[PoliticalFamily.LR], [PoliticalFamily.RNx]]
        }
        with pytest.raises(ValueError, match="ne couvre pas"):
            direct_kernel_model(transfer_orderings=incomplete)


class TestSimulationParameters:
    def test_les_parametres_globaux_sont_valides(self):
        draw = build("national", seed=0).draw_simulation()
        assert 0.5 <= draw.alpha <= 1.0
        assert 0 < draw.non_expressed_retention < 1
        assert 0 < draw.qualified_demobilisation < 1
        assert 0 <= draw.mixing_weight <= 1
        assert -1.0 <= draw.tilt <= 2.0
        assert set(draw.extensions) == set(DEFAULT_TRANSFER_ORDERINGS)
        for source, extension in draw.extensions.items():
            assert set(extension) == set(DESTINATIONS) - {source} - set(
                DEFAULT_FREE_TARGETS
            )

    def test_un_tirage_fourni_est_bien_celui_qui_sert(self, districts):
        """`alpha` vient du tirage, pas d'un attribut : le forcer très haut
        concentre les lignes vers le centre de la région ordonnée.

        Un modèle NEUF à chaque itération : réutiliser le même ferait avancer son
        générateur entre les deux appels, et l'on mesurerait cette dérive plutôt
        que l'effet d'alpha."""
        spread = {}
        for alpha in (1.0, 500.0):
            model = build("national", seed=0)
            draw = replace(model.draw_simulation(), alpha=alpha)
            row = model.sample_transfer_matrices(districts, draw)[0].rates[
                PoliticalFamily.ENSx
            ]
            spread[alpha] = max(row.values()) - min(row.values())
        assert spread[500.0] < spread[1.0]

    @pytest.mark.parametrize("name", ["national_anchored", "kernel_anchored"])
    def test_les_variantes_ancrees_conditionnent_la_retention(self, name, districts):
        """L'ancre conserve l'information du prior : deux points de départ
        différents peuvent atteindre la même cible par des compromis différents."""
        rows = {}
        for retention in (0.1, 0.9):
            model = build_for_test(name, seed=0)
            draw = replace(model.draw_simulation(), non_expressed_retention=retention)
            matrices = model.sample_transfer_matrices(districts, draw)
            rows[retention] = matrices[0].rates[NON_EXPRIMES][NON_EXPRIMES]
        assert rows[0.1] < rows[0.9]

    def test_la_variante_non_ancree_utilise_la_retention_du_tirage(self, districts):
        model = build("national", seed=0)
        draw = replace(model.draw_simulation(), non_expressed_retention=0.42)
        matrices = model.sample_transfer_matrices(districts, draw)
        assert matrices[0].rates[NON_EXPRIMES][NON_EXPRIMES] == pytest.approx(0.42)
