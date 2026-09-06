"""
Ce que `config/model.yaml` a le droit de contenir.

Ces tests portent sur le SCHÉMA, pas sur les valeurs du scrutin : ils décrivent
les fautes de saisie qu'un fichier de configuration doit rendre impossibles.
Avant le schéma pydantic, `priors.mixing_beta` n'était validé nulle part — une
liste de trois valeurs ou un paramètre négatif passait le chargement, restait
silencieux sur `national_anchored` (qui n'utilise pas ce prior) et cassait au
fond de la boucle de simulation sur `kernel_anchored`, avec un message qui ne
nommait ni le fichier ni le champ.
"""

import copy

import pytest
import yaml

from analyse_legislatives.config import (
    MODEL_CONFIG,
    MODEL_CONFIG_PATH,
    load_model_config,
)
from analyse_legislatives.parties import NON_EXPRIMES, DESTINATIONS, PoliticalFamily


@pytest.fixture
def raw():
    return yaml.safe_load(MODEL_CONFIG_PATH.read_text(encoding="utf-8"))


def write(tmp_path, config):
    path = tmp_path / "model.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


def load_broken(tmp_path, raw, mutate):
    """Applique une faute de saisie et renvoie le message d'erreur."""
    config = copy.deepcopy(raw)
    mutate(config)
    with pytest.raises(ValueError) as excinfo:
        load_model_config(write(tmp_path, config))
    return str(excinfo.value)


def test_le_fichier_du_depot_est_valide():
    assert load_model_config() == MODEL_CONFIG


def test_les_labels_deviennent_des_objets_du_domaine():
    """Le YAML ne contient que des chaînes ; le reste du code indexe des
    `PoliticalFamily`. La conversion est la raison d'être de ce module."""
    assert all(
        isinstance(source, PoliticalFamily)
        for source in MODEL_CONFIG.transfer_orderings
    )
    targets = {
        target
        for tiers in MODEL_CONFIG.transfer_orderings.values()
        for tier in tiers
        for target in tier
    }
    assert targets <= set(DESTINATIONS)
    assert NON_EXPRIMES in targets, "les non-exprimés sont une destination ordonnée"


@pytest.mark.parametrize(
    "prior",
    [
        "non_expressed_retention_beta",
        "qualified_demobilisation_beta",
        "mixing_beta",
    ],
)
def test_un_prior_beta_refuse_une_longueur_autre_que_deux(tmp_path, raw, prior):
    def mutate(config):
        config["priors"][prior] = [2.0, 2.0, 1.0]

    message = load_broken(tmp_path, raw, mutate)
    assert prior in message
    assert str(MODEL_CONFIG_PATH.name) in message or "model.yaml" in message


@pytest.mark.parametrize(
    "prior",
    [
        "non_expressed_retention_beta",
        "qualified_demobilisation_beta",
        "mixing_beta",
    ],
)
def test_un_prior_beta_refuse_un_parametre_negatif(tmp_path, raw, prior):
    def mutate(config):
        config["priors"][prior] = [-1.0, 2.0]

    assert prior in load_broken(tmp_path, raw, mutate)


def test_les_bornes_doivent_etre_croissantes(tmp_path, raw):
    def mutate(config):
        config["priors"]["dirichlet_alpha_bounds"] = [1.0, 0.5]

    assert "croissantes" in load_broken(tmp_path, raw, mutate)


def test_une_cle_mal_orthographiee_est_refusee(tmp_path, raw):
    """Sans `extra="forbid"`, la clé fautive serait ignorée en silence — le pire
    des cas pour un fichier censé être la source de vérité."""

    def mutate(config):
        config["n_simulation"] = config.pop("n_simulations")

    message = load_broken(tmp_path, raw, mutate)
    assert "n_simulation" in message


def test_une_destination_inconnue_est_refusee(tmp_path, raw):
    def mutate(config):
        config["transfer_orderings"]["ENS+"][0][0] = "PS"

    message = load_broken(tmp_path, raw, mutate)
    assert "transfer_orderings" in message and "PS" in message


def test_un_nombre_de_simulations_nul_est_refuse(tmp_path, raw):
    def mutate(config):
        config["n_simulations"] = 0

    assert "n_simulations" in load_broken(tmp_path, raw, mutate)


def test_une_racine_non_mapping_est_refusee(tmp_path):
    path = tmp_path / "model.yaml"
    path.write_text("- pas un mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping YAML"):
        load_model_config(path)


def test_la_baisse_de_participation_attendue_peut_etre_negative(tmp_path, raw):
    """Garde-fou contre un `PositiveFloat` posé par réflexe : la participation
    baisse habituellement au 2nd tour, donc ce champ est négatif dans le dépôt."""
    config = copy.deepcopy(raw)
    config["expressed_share"]["expected_change_pts"] = -4.34
    assert (
        load_model_config(write(tmp_path, config)).expressed_share.expected_change_pts
        < 0
    )
