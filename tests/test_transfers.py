"""
Invariants de `normalize_for_district` — le code le plus subtil du dépôt.

Chaque test correspond à une propriété dont la violation a déjà, ou aurait,
produit un résultat faux silencieusement (voir les commentaires de
`transfers.py`) : une ligne mal normalisée n'échoue pas, elle déverse tout le
réservoir dans la dernière colonne (l'abstention).
"""

import numpy as np
import pytest

from analyse_legislatives.parties import NON_EXPRIMES, DESTINATIONS, PoliticalFamily
from analyse_legislatives.transfers import TransferMatrix, normalize_for_district
from tests.conftest import make_district


def rows_of(normalized: TransferMatrix, district):
    """Lignes de la matrice normalisée, dans l'ordre de la circonscription."""
    order = list(district.competing_parties_results)
    return {source: normalized.rates[source] for source in order}


class TestNormalizationInvariants:
    def test_every_row_sums_to_one(self, matrix, duel):
        """Précondition dure du tirage multinomial : une somme différente de 1
        est versée en silence dans la dernière colonne."""
        normalized = normalize_for_district(matrix, duel, 0.5)
        for source, row in rows_of(normalized, duel).items():
            assert sum(row.values()) == pytest.approx(1.0), f"ligne {source}"

    def test_rows_sum_to_one_in_triangulaire(self, matrix, triangulaire):
        normalized = normalize_for_district(matrix, triangulaire, 0.5)
        for source, row in rows_of(normalized, triangulaire).items():
            assert sum(row.values()) == pytest.approx(1.0), f"ligne {source}"

    def test_no_transfer_to_eliminated_parties(self, matrix, duel):
        """Les colonnes des partis non qualifiés doivent être vides : un report
        vers un candidat absent du 2nd tour serait des voix perdues."""
        normalized = normalize_for_district(matrix, duel, 0.5)
        qualified = {PoliticalFamily.NFPx, PoliticalFamily.RNx, NON_EXPRIMES}
        for source, row in normalized.rates.items():
            for target, rate in row.items():
                if target not in qualified:
                    assert rate == 0.0, f"{source} -> {target}"

    def test_qualified_parties_keep_their_own_votes(self, matrix, duel):
        """Une famille qualifiée garde ses voix (ligne identité) : sans ça, le
        cas « deux candidats d'une même famille, un seul qualifié » envoyait tout
        le réservoir à l'abstention — 886 000 voix nationalement."""
        normalized = normalize_for_district(matrix, duel, 0.5)
        for party in (PoliticalFamily.NFPx, PoliticalFamily.RNx):
            assert normalized.rates[party][party] == 1.0
            assert sum(normalized.rates[party].values()) == 1.0


class TestAbstentionRow:
    def test_retention_is_a_direct_probability(self, matrix, duel):
        """`non_expressed_retention` doit se retrouver tel quel, sans être renormalisé
        contre le nombre de qualifiés — sinon la rétention atteignable dépend de
        la configuration locale, ce qui est un artefact."""
        normalized = normalize_for_district(matrix, duel, 0.5)
        assert normalized.rates[NON_EXPRIMES][NON_EXPRIMES] == pytest.approx(0.9)

    def test_retention_independent_of_number_of_competitors(
        self, matrix, duel, triangulaire
    ):
        duel_row = normalize_for_district(matrix, duel, 0.5).rates[NON_EXPRIMES]
        tri_row = normalize_for_district(matrix, triangulaire, 0.5).rates[NON_EXPRIMES]
        assert duel_row[NON_EXPRIMES] == pytest.approx(tri_row[NON_EXPRIMES])

    def test_tilt_zero_splits_evenly(self, matrix, duel):
        """`non_expressed_tilt` = 0 : tous les poids valent 1, donc parts égales entre
        qualifiés quels que soient leurs scores du 1er tour — c'est l'ancienne
        règle uniforme, désormais un cas particulier et non plus la règle."""
        row = normalize_for_district(matrix, duel, 0.0).rates[NON_EXPRIMES]
        assert row[PoliticalFamily.NFPx] == pytest.approx(row[PoliticalFamily.RNx])
        assert row[PoliticalFamily.NFPx] == pytest.approx((1 - 0.9) / 2)

    def test_tilt_one_follows_first_round(self, matrix, duel):
        """`non_expressed_tilt` = 1 : poids égaux aux scores (règle PROPORTIONNELLE), ici
        10 000 contre 9 000."""
        row = normalize_for_district(matrix, duel, 1.0).rates[NON_EXPRIMES]
        mobilized = 1 - 0.9
        assert row[PoliticalFamily.NFPx] == pytest.approx(mobilized * 10_000 / 19_000)
        assert row[PoliticalFamily.RNx] == pytest.approx(mobilized * 9_000 / 19_000)

    def test_negative_tilt_favours_the_local_underdog(self, matrix, duel):
        """La région qu'aucune des deux règles candidates ne pouvait atteindre :
        les mobilisés vont majoritairement au second."""
        row = normalize_for_district(matrix, duel, -1.0).rates[NON_EXPRIMES]
        assert row[PoliticalFamily.RNx] > row[PoliticalFamily.NFPx]

    def test_leader_share_increases_monotonically_with_tilt(self, matrix, duel):
        """`non_expressed_tilt` est un curseur continu : la part du leader local croît avec
        lui, sans discontinuité entre les cas particuliers."""
        shares = [
            normalize_for_district(matrix, duel, t).rates[NON_EXPRIMES][
                PoliticalFamily.NFPx
            ]
            for t in (-1.0, -0.5, 0.0, 0.5, 1.0, 2.0)
        ]
        assert shares == sorted(shares)

    @pytest.mark.parametrize("tilt", [-1.0, -0.5, 0.0, 1.0, 2.0])
    def test_row_sums_to_one_for_any_tilt(self, matrix, duel, tilt):
        row = normalize_for_district(matrix, duel, tilt).rates[NON_EXPRIMES]
        assert sum(row.values()) == pytest.approx(1.0)

    def test_non_qualified_never_receive_abstainers_at_negative_tilt(self, matrix):
        """Un exposant négatif élèverait 0 à une puissance négative — donc +inf, et
        tout le réservoir irait à un parti absent du 2nd tour. Les non-qualifiés
        doivent être masqués AVANT l'exponentiation."""
        district = make_district(
            competing={PoliticalFamily.NFPx: 10_000, PoliticalFamily.RNx: 9_000},
            non_expressed=5_000,
        )
        row = normalize_for_district(matrix, district, -1.0).rates[NON_EXPRIMES]
        for party in (PoliticalFamily.ENSx, PoliticalFamily.LR, PoliticalFamily.DIV):
            assert row[party] == 0.0
        assert np.isfinite(list(row.values())).all()

    def test_tiny_but_positive_row_is_still_normalised(self, duel):
        """
        Régression : une ligne dont les cellules SURVIVANTES sont minuscules doit
        quand même être renormalisée.

        Une ligne complète somme à 1, mais restreinte aux seuls qualifiés elle peut
        sommer à 1e-30 : même avec alpha=1, certains tirages exponentiels peuvent
        être numériquement très proches de zéro, et
        si la masse est allée à des partis absents du 2nd tour il ne reste presque
        rien. C'est un rapport de mélange parfaitement défini. L'ancien garde-fou
        (somme <= 1e-12 traitée comme nulle) rendait la ligne nulle, et le tirage
        multinomial échouait ensuite sur « Ligne de report non normalisée ».
        """
        tiny = TransferMatrix(
            {
                PoliticalFamily.ENSx: {
                    PoliticalFamily.NFPx: 1e-30,
                    PoliticalFamily.RNx: 4e-31,
                    NON_EXPRIMES: 2e-31,
                    PoliticalFamily.LR: 0.9,
                },
                NON_EXPRIMES: {NON_EXPRIMES: 0.9},
            }
        )
        row = normalize_for_district(tiny, duel, 0.5).rates[PoliticalFamily.ENSx]
        assert sum(row.values()) == pytest.approx(1.0)
        # et les proportions relatives sont préservées
        assert row[PoliticalFamily.NFPx] == pytest.approx(1e-30 / 1.6e-30, rel=1e-6)

    def test_genuinely_empty_row_stays_empty(self, duel):
        """Le pendant : une ligne réellement nulle ne doit pas devenir une
        distribution uniforme au passage."""
        empty = TransferMatrix(
            {
                PoliticalFamily.ENSx: dict.fromkeys(DESTINATIONS, 0.0),
                NON_EXPRIMES: {NON_EXPRIMES: 0.9},
            }
        )
        row = normalize_for_district(empty, duel, 0.5).rates[PoliticalFamily.ENSx]
        assert sum(row.values()) == 0.0

    def test_district_with_no_competitor_keeps_everyone_abstained(self, matrix):
        """Cas dégénéré : sans aucun qualifié, l'abstention reste entière plutôt
        que de produire une division par zéro."""
        empty = make_district(competing={}, non_expressed=1_000)
        row = normalize_for_district(matrix, empty, 0.5).rates[NON_EXPRIMES]
        assert row[NON_EXPRIMES] == 1.0
        assert sum(row.values()) == pytest.approx(1.0)


class TestTransferMatrix:

    def test_matrix_roundtrip(self, matrix):
        restored = TransferMatrix.from_matrix(matrix.to_matrix())
        assert restored.to_matrix() == pytest.approx(matrix.to_matrix())

    def test_diagonal_is_zero_except_abstention(self, matrix):
        dense = matrix.to_matrix()
        diagonal = np.diag(dense)
        assert (diagonal[:-1] == 0).all(), "un parti ne se reporte pas sur lui-même"
        assert diagonal[-1] == pytest.approx(
            0.9
        ), "sauf NON_EXPRIMES : c'est la rétention"

    def test_normalization_emits_no_numpy_warning(self, matrix, duel):
        """Les lignes entièrement nulles donnaient un 0/0, donc un RuntimeWarning
        à chaque appel, rattrapé après coup par `nan_to_num`."""
        with np.errstate(all="raise"):
            normalize_for_district(matrix, duel, 0.5)
