"""Construction de lignes de report à partir d'ordres de préférence.

HYPOTHÈSE 2 du billet (`writeup.fr.md`) : les reports sont contraints par un ORDRE
de préférence déclaré par groupe politique, et par rien d'autre — aucun taux moyen
n'est fixé. Les ordres eux-mêmes sont dans `config/model.yaml`.

Normaliser des Gamma indépendantes produit une Dirichlet symétrique. Trier ses
coordonnées échangeables donne exactement cette loi conditionnée à la région du
simplexe qui respecte l'ordre déclaré.
"""

from collections.abc import Mapping, Sequence

import numpy as np
from scipy.stats import expon as _expon_dist
from scipy.stats import gamma as _gamma_dist

from analyse_legislatives.parties import Destination

GAMMA_UNIFORM_FLOOR = 1e-12
"""Les uniformes sont pincées loin de 0 et de 1 : la fonction quantile Gamma y
diverge, et une valeur infinie contaminerait toute la ligne à la normalisation."""


def linear_extension(
    tiers: Sequence[Sequence[Destination]], rng: np.random.Generator
) -> list[Destination]:
    """Tire un ordre total compatible avec les paliers de l'ordre partiel."""
    extension: list[Destination] = []
    for tier in tiers:
        order = rng.permutation(len(tier))
        extension.extend(tier[i] for i in order)
    return extension


def draw_alpha(
    bounds: tuple[float, float],
    rng: np.random.Generator,
    override: float | None = None,
) -> float:
    """Tire la concentration log-uniformément, sauf si elle est imposée."""
    if override is not None:
        return float(override)
    low, high = bounds
    return float(np.exp(rng.uniform(np.log(low), np.log(high))))


def uniforms_to_gammas(
    uniforms: Mapping[Destination, np.ndarray], alpha: float
) -> dict[Destination, np.ndarray]:
    """Applique la quantile Gamma sans modifier la copule des uniformes."""
    clipped = {
        target: np.clip(u, GAMMA_UNIFORM_FLOOR, 1 - GAMMA_UNIFORM_FLOOR)
        for target, u in uniforms.items()
    }
    if alpha == 1:
        return {target: _expon_dist.ppf(u) for target, u in clipped.items()}
    return {target: _gamma_dist.ppf(u, alpha) for target, u in clipped.items()}


def gammas_to_row(
    gammas: Mapping[Destination, np.ndarray],
    extension: Sequence[Destination],
    free_targets: Sequence[Destination] = (),
) -> dict[Destination, np.ndarray]:
    """Normalise les Gamma et ordonne seulement les destinations contraintes."""
    targets = list(extension) + list(free_targets)
    values = np.array([gammas[target] for target in targets])
    shares = values / values.sum(axis=0)

    n_ordered = len(extension)
    # i-ème plus grande part -> i-ème destination par ordre de préférence
    ranked = -np.sort(-shares[:n_ordered], axis=0)
    row = {target: ranked[i] for i, target in enumerate(extension)}
    row.update({target: shares[n_ordered + j] for j, target in enumerate(free_targets)})
    return row
