"""Artefact numérique consommé par l'application Streamlit.

La simulation est une étape de reproduction hors ligne. L'application ne doit
jamais la relancer sur le serveur : elle charge ce paquet, vérifie qu'il
correspond exactement à sa configuration, puis ne fait que des agrégations
légères.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from analyse_legislatives.parties import DESTINATIONS
from analyse_legislatives.transfers import TransferMatrix

SCHEMA_VERSION = 1
DATA_FILENAME = "simulations.npz"
MANIFEST_FILENAME = "manifest.json"


class AppArtifactError(RuntimeError):
    """Artefact absent, illisible ou incompatible avec l'application."""


@dataclass(frozen=True)
class AppArtifact:
    cube: np.ndarray
    prior_matrix: TransferMatrix
    manifest: Mapping[str, Any]


def _labels() -> list[str]:
    return [str(destination) for destination in DESTINATIONS]


def write_app_artifact(
    directory: Path,
    *,
    cube: np.ndarray,
    prior_matrix: TransferMatrix,
    model: str,
    seed: int,
    config_sha256: str,
    district_ids: Sequence[str],
) -> None:
    """Écrit le cube compressé et son manifeste de compatibilité."""
    values = np.asarray(cube)
    if values.ndim != 3:
        raise ValueError(f"Cube de forme {values.shape}, attendu un tableau 3D.")
    expected_shape = (values.shape[0], len(district_ids), len(DESTINATIONS))
    if values.shape != expected_shape:
        raise ValueError(
            f"Cube de forme {values.shape}, attendu (*, {len(district_ids)}, "
            f"{len(DESTINATIONS)})."
        )
    if not np.issubdtype(values.dtype, np.integer):
        raise ValueError("Le cube doit contenir des nombres entiers de voix.")
    if values.size and (values.min() < 0 or values.max() > np.iinfo(np.int32).max):
        raise ValueError("Le cube ne peut pas être encodé sans perte en int32.")

    matrix = prior_matrix.to_matrix()
    matrix_shape = (len(DESTINATIONS), len(DESTINATIONS))
    if matrix.shape != matrix_shape:
        raise ValueError(f"Matrice de forme {matrix.shape}, attendu {matrix_shape}.")

    directory.mkdir(parents=True, exist_ok=True)
    data_path = directory / DATA_FILENAME
    temporary_data_path = directory / f".{DATA_FILENAME}.tmp.npz"
    np.savez_compressed(
        temporary_data_path,
        cube=values.astype(np.int32, copy=False),
        prior_matrix=matrix.astype(np.float64, copy=False),
    )
    temporary_data_path.replace(data_path)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "seed": seed,
        "n_simulations": int(values.shape[0]),
        "config_sha256": config_sha256,
        "district_ids": list(district_ids),
        "destinations": _labels(),
        "cube_shape": list(values.shape),
        "cube_dtype": "int32",
        "data_file": DATA_FILENAME,
    }
    manifest_path = directory / MANIFEST_FILENAME
    temporary_manifest_path = directory / f".{MANIFEST_FILENAME}.tmp"
    temporary_manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary_manifest_path.replace(manifest_path)


def _read_manifest(directory: Path) -> dict[str, Any]:
    path = directory / MANIFEST_FILENAME
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AppArtifactError(
            f"Artefact applicatif absent ({path}). Lancez `python scripts/reproduce.py` "
            "avant de déployer l'application."
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AppArtifactError(f"Manifeste applicatif illisible : {path}.") from exc
    if not isinstance(manifest, dict):
        raise AppArtifactError(f"Manifeste applicatif invalide : {path}.")
    return manifest


def _require(manifest: Mapping[str, Any], field: str, expected: Any) -> None:
    observed = manifest.get(field)
    if observed != expected:
        raise AppArtifactError(
            f"Artefact applicatif incompatible : `{field}` vaut {observed!r}, "
            f"attendu {expected!r}. Relancez `python scripts/reproduce.py`."
        )


def load_app_artifact(
    directory: Path,
    *,
    expected_model: str,
    expected_seed: int,
    expected_n_simulations: int,
    expected_config_sha256: str,
    expected_district_ids: Sequence[str],
) -> AppArtifact:
    """Charge et valide l'artefact, sans aucun repli vers un calcul."""
    manifest = _read_manifest(directory)
    _require(manifest, "schema_version", SCHEMA_VERSION)
    _require(manifest, "model", expected_model)
    _require(manifest, "seed", expected_seed)
    _require(manifest, "n_simulations", expected_n_simulations)
    _require(manifest, "config_sha256", expected_config_sha256)
    _require(manifest, "district_ids", list(expected_district_ids))
    _require(manifest, "destinations", _labels())

    expected_shape = (
        expected_n_simulations,
        len(expected_district_ids),
        len(DESTINATIONS),
    )
    _require(manifest, "cube_shape", list(expected_shape))
    _require(manifest, "cube_dtype", "int32")
    _require(manifest, "data_file", DATA_FILENAME)

    data_path = directory / DATA_FILENAME
    try:
        with np.load(data_path, allow_pickle=False) as archive:
            cube = np.array(archive["cube"], copy=True)
            matrix = np.array(archive["prior_matrix"], copy=True)
    except (FileNotFoundError, OSError, KeyError, ValueError) as exc:
        raise AppArtifactError(
            f"Données applicatives illisibles : {data_path}."
        ) from exc

    if cube.shape != expected_shape or cube.dtype != np.int32:
        raise AppArtifactError(
            f"Cube applicatif invalide : forme {cube.shape}, dtype {cube.dtype}."
        )
    expected_matrix_shape = (len(DESTINATIONS), len(DESTINATIONS))
    if matrix.shape != expected_matrix_shape:
        raise AppArtifactError(
            f"Matrice prédictive invalide : forme {matrix.shape}, "
            f"attendu {expected_matrix_shape}."
        )

    cube.flags.writeable = False
    matrix.flags.writeable = False
    return AppArtifact(
        cube=cube,
        prior_matrix=TransferMatrix.from_matrix(matrix),
        manifest=manifest,
    )
