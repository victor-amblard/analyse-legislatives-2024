"""Paquet de simulations précalculé consommé par la petite VM."""

import json

import numpy as np
import pytest

from analyse_legislatives.app_artifacts import (
    AppArtifactError,
    MANIFEST_FILENAME,
    load_app_artifact,
    write_app_artifact,
)
from analyse_legislatives.parties import DESTINATIONS
from analyse_legislatives.transfers import TransferMatrix


def artifact_values():
    cube = np.arange(3 * 2 * len(DESTINATIONS), dtype=np.int64).reshape(
        3, 2, len(DESTINATIONS)
    )
    matrix = TransferMatrix.from_matrix(np.eye(len(DESTINATIONS)))
    return cube, matrix


def write_valid(tmp_path):
    cube, matrix = artifact_values()
    write_app_artifact(
        tmp_path,
        cube=cube,
        prior_matrix=matrix,
        model="national_anchored",
        seed=7,
        config_sha256="abc",
        district_ids=["01", "02"],
    )
    return cube


def load_valid(tmp_path):
    return load_app_artifact(
        tmp_path,
        expected_model="national_anchored",
        expected_seed=7,
        expected_n_simulations=3,
        expected_config_sha256="abc",
        expected_district_ids=["01", "02"],
    )


def test_roundtrip_compresses_to_int32_and_preserves_votes(tmp_path):
    expected = write_valid(tmp_path)
    artifact = load_valid(tmp_path)
    assert artifact.cube.dtype == np.int32
    assert np.array_equal(artifact.cube, expected)
    assert not artifact.cube.flags.writeable


def test_missing_artifact_never_falls_back_to_a_simulation(tmp_path):
    with pytest.raises(AppArtifactError, match="reproduce.py"):
        load_valid(tmp_path)


def test_stale_configuration_is_rejected(tmp_path):
    write_valid(tmp_path)
    manifest_path = tmp_path / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["config_sha256"] = "old"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(AppArtifactError, match="config_sha256"):
        load_valid(tmp_path)


def test_values_larger_than_int32_are_rejected(tmp_path):
    cube, matrix = artifact_values()
    cube[0, 0, 0] = np.iinfo(np.int32).max + 1
    with pytest.raises(ValueError, match="int32"):
        write_app_artifact(
            tmp_path,
            cube=cube,
            prior_matrix=matrix,
            model="national_anchored",
            seed=7,
            config_sha256="abc",
            district_ids=["01", "02"],
        )
