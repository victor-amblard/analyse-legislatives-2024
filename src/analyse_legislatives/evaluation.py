"""Métriques pures pour évaluer des distributions prédictives simulées."""

import numpy.typing as npt
import numpy as np
from scipy.spatial.distance import cdist, pdist


def coverage_and_width(
    samples: np.ndarray, truth: np.ndarray, level: float
) -> tuple[float, float]:
    """Couverture et largeur moyenne des intervalles centraux de niveau ``level``."""
    lo = np.quantile(samples, (1 - level) / 2, axis=0)
    hi = np.quantile(samples, (1 + level) / 2, axis=0)
    return float(((truth >= lo) & (truth <= hi)).mean()), float((hi - lo).mean())


def pit(samples: np.ndarray, truth: np.ndarray) -> np.ndarray:
    """Rang de chaque observation dans sa distribution prédictive simulée."""
    return (samples < truth[None, :]).mean(axis=0)


def energy_score(samples: npt.ArrayLike, truth: npt.ArrayLike) -> float:
    """Energy score multivarié, estimé avec la correction ``fair``."""
    samples = np.atleast_2d(np.asarray(samples, dtype=float))
    truth = np.atleast_1d(np.asarray(truth, dtype=float))
    n = samples.shape[0]
    if n < 2:
        raise ValueError("L'energy score requiert au moins deux tirages.")
    distance_to_truth = np.linalg.norm(samples - truth, axis=1).mean()
    half_spread = pdist(samples).sum() / (n * (n - 1))
    return float(distance_to_truth - half_spread)


def probabilistic_and_median_scores(
    samples: np.ndarray, truth: np.ndarray
) -> tuple[float, float]:
    """Energy score probabiliste et distance du scénario médian à la vérité."""
    probabilistic = energy_score(samples, truth)
    deterministic = float(np.linalg.norm(np.median(samples, axis=0) - truth))
    return probabilistic, deterministic


def joint_region_scores(
    samples: np.ndarray, truth: np.ndarray
) -> tuple[np.ndarray, float, float]:
    """
    Objectif = Estimer une région prédictive jointe (plutôt que des produits
    d'intervalles marginaux).

    """
    if samples.shape[0] < 4:
        raise ValueError("La région prédictive jointe requiert au moins 4 tirages.")

    reference = samples[::2]
    calibration = samples[1::2]
    half_spread = pdist(reference).sum() / (
        reference.shape[0] * (reference.shape[0] - 1)
    )
    calibration_scores = cdist(calibration, reference).mean(axis=1) - half_spread
    observed_score = float(cdist(truth[None, :], reference).mean() - half_spread)
    percentile = (1 + np.count_nonzero(calibration_scores <= observed_score)) / (
        calibration_scores.size + 1
    )
    return calibration_scores, observed_score, float(percentile)
