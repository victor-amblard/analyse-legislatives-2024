"""
Les contraintes scalaires partagées, et le fait qu'elles s'appliquent des deux côtés.

`config/model.yaml` et l'instanciation directe d'un `Model` sont deux portes
d'entrée pour les mêmes couples de flottants. Elles doivent refuser exactement
les mêmes valeurs : ces tests vérifient qu'elles passent bien par la même
implémentation plutôt que par deux copies appelées à diverger.
"""

import numpy as np
import pytest

from analyse_legislatives.config import DEFAULT_FREE_TARGETS, DEFAULT_TRANSFER_ORDERINGS
from analyse_legislatives.models import MODELS
from analyse_legislatives.utils.validation import (
    check_beta_pair,
    check_bounds,
    check_positive_bounds,
)

VALID_MODEL_ARGUMENTS = {
    "transfer_orderings": DEFAULT_TRANSFER_ORDERINGS,
    "non_expressed_tilt_bounds": (-1.0, 2.0),
    "non_expressed_retention_prior": (8.0, 2.0),
    "qualified_demobilisation_prior": (2.0, 38.0),
    "mixing_prior": (2.0, 2.0),
    "dirichlet_alpha_bounds": (0.5, 1.0),
    "free_targets": DEFAULT_FREE_TARGETS,
}


def build_national(**overrides):
    arguments = VALID_MODEL_ARGUMENTS | overrides
    return MODELS["national"](rng=np.random.default_rng(0), **arguments)


class TestCheckBetaPair:
    @pytest.mark.parametrize("value", [(0.0, 2.0), (2.0, 0.0), (-1.0, 2.0)])
    def test_refuse_un_parametre_non_strictement_positif(self, value):
        with pytest.raises(ValueError, match="strictement positifs"):
            check_beta_pair(value)

    @pytest.mark.parametrize("value", [(1.0,), (1.0, 2.0, 3.0), 1.0])
    def test_refuse_une_longueur_autre_que_deux(self, value):
        with pytest.raises(ValueError, match="exactement deux valeurs"):
            check_beta_pair(value)

    def test_le_nom_apparait_dans_le_message(self):
        with pytest.raises(ValueError, match="mixing_prior"):
            check_beta_pair((-1.0, 2.0), "mixing_prior")


class TestCheckBounds:
    @pytest.mark.parametrize("value", [(2.0, -1.0), (1.0, 1.0)])
    def test_refuse_des_bornes_non_croissantes(self, value):
        with pytest.raises(ValueError, match="croissantes"):
            check_bounds(value)

    def test_accepte_une_borne_negative(self):
        """`non_expressed_tilt_uniform` vaut [-1, 2] : le signe est libre."""
        assert check_bounds((-1.0, 2.0)) == (-1.0, 2.0)

    @pytest.mark.parametrize("value", [(0.0, 1.0), (1.0, 0.5), (1.0, 1.0)])
    def test_les_bornes_positives_exigent_les_deux_proprietes(self, value):
        with pytest.raises(ValueError, match="strictement positives et croissantes"):
            check_positive_bounds(value)


class TestLesDeuxPortesRefusentLesMemesValeurs:
    """Un modèle construit à la main ne passe pas par le schéma pydantic : sans
    ces contrôles, une valeur invalide n'échouait qu'au tirage, parfois plusieurs
    minutes plus tard, et seulement sur les variantes qui consomment ce prior."""

    @pytest.mark.parametrize(
        "field",
        [
            "non_expressed_retention_prior",
            "qualified_demobilisation_prior",
            "mixing_prior",
        ],
    )
    def test_un_prior_beta_invalide_est_refuse_a_la_construction(self, field):
        with pytest.raises(ValueError, match=field):
            build_national(**{field: (-1.0, 2.0)})
        with pytest.raises(ValueError, match=field):
            build_national(**{field: (2.0, 2.0, 1.0)})

    def test_les_bornes_de_tilt_inversees_sont_refusees(self):
        """Non validées auparavant : `Generator.uniform` tire sans broncher dans
        un intervalle retourné, ce qui inverse la croyance en silence."""
        with pytest.raises(ValueError, match="non_expressed_tilt_bounds"):
            build_national(non_expressed_tilt_bounds=(2.0, -1.0))
