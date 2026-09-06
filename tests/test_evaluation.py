"""Tests des métriques prédictives partagées par les scripts."""

import numpy as np
import pytest

from analyse_legislatives.evaluation import (
    coverage_and_width,
    energy_score,
    joint_region_scores,
)


def test_energy_score_is_zero_for_a_perfect_constant_forecast():
    samples = np.repeat([[1.0, 2.0]], repeats=5, axis=0)
    assert energy_score(samples, np.array([1.0, 2.0])) == pytest.approx(0.0)


def test_energy_score_requires_two_draws():
    with pytest.raises(ValueError, match="au moins deux"):
        energy_score(np.array([[1.0]]), np.array([1.0]))


def test_coverage_and_width_use_central_intervals():
    samples = np.arange(10, dtype=float)[:, None]
    coverage, width = coverage_and_width(samples, np.array([4.5]), 0.8)
    assert coverage == 1.0
    assert width == pytest.approx(7.2)


def test_joint_region_requires_reference_and_calibration_draws():
    with pytest.raises(ValueError, match="au moins 4"):
        joint_region_scores(np.ones((3, 2)), np.ones(2))
