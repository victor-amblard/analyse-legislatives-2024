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
from scipy.special import gammaincinv

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


def extension_ranks(
    tiers: Sequence[Sequence[Destination]],
    scores: Mapping[Destination, np.ndarray],
) -> tuple[list[Destination], np.ndarray]:
    """Ordre total PAR CIRCONSCRIPTION, départagé par des scores latents.

    Version locale de `linear_extension`. Trier des variables continues
    échangeables tire une permutation uniforme : à circonscription fixée, si les
    scores d'un même palier sont i.i.d., la loi de l'ordre obtenu est exactement
    celle de `rng.permutation`. Corréler ces scores entre circonscriptions ne
    change donc RIEN à la loi marginale de l'ordre — seulement sa dépendance,
    exactement comme le copule gaussien le fait pour les cellules d'une ligne.

    Renvoie la liste canonique des destinations ordonnées (paliers concaténés) et
    un tableau `ranks` tel que `ranks[i, c]` est le rang, dans la circonscription
    `c`, de la i-ème destination de cette liste. Le rang 0 est la destination la
    plus préférée, qui reçoit la plus grande part.
    """
    ordered = [target for tier in tiers for target in tier]
    n = len(next(iter(scores.values())))
    ranks = np.empty((len(ordered), n), dtype=np.intp)

    start = 0
    for tier in tiers:
        size = len(tier)
        if size == 1:
            # Aucun ex aequo à départager : le rang ne dépend pas du tirage.
            ranks[start] = start
        else:
            z = np.array([scores[target] for target in tier])
            # Le plus grand score prend le créneau le plus préféré du palier.
            order = np.argsort(-z, axis=0)
            slots = np.broadcast_to(
                np.arange(start, start + size, dtype=np.intp)[:, None], (size, n)
            )
            np.put_along_axis(ranks[start : start + size], order, slots, axis=0)
        start += size

    return ordered, ranks


def bounds_for_target(
    row: Mapping[Destination, float],
    tiers: Sequence[Sequence[Destination]],
    target: Destination,
) -> tuple[float, float]:
    """Jusqu'où `target` peut bouger sans quitter la région de l'ordre déclaré.

    Pendant de `gammas_to_row` : celle-ci CONSTRUIT une ligne dans la région du
    simplexe compatible avec l'ordre, celle-ci dit de quelle MARGE une cellule y
    dispose encore. Les deux encodent la même contrainte et doivent donc être
    relues ensemble si l'ordre cesse d'être une contrainte dure.

    On suppose que toutes les AUTRES cellules seront remises à l'échelle par un
    même facteur — ce que fait un tilt exponentiel d'une seule cellule. Leurs
    rapports restent intacts, et seules les inégalités qui séparent `target` de
    ses paliers voisins peuvent devenir actives.

    Les bornes portent sur la ligne BRUTE. Un appelant qui restreint ensuite la
    ligne aux candidats réellement présents doit les convertir lui-même : la
    restriction renormalise, donc déplace les parts.
    """
    target_tier = next(
        (index for index, tier in enumerate(tiers) if target in tier), None
    )
    if target_tier is None:
        return 0.0, 1.0

    share = float(row[target])
    other_mass = 1.0 - share
    if other_mass <= 0:
        return 1.0, 1.0

    floor, ceiling = 0.0, 1.0
    for index, tier in enumerate(tiers):
        if index == target_tier:
            continue
        for other in tier:
            other_share = row[other]
            # Part à laquelle `target` rattraperait exactement `other`, une fois
            # le reste de la ligne renormalisé.
            tie_share = other_share / (other_mass + other_share)
            if index < target_tier:
                ceiling = min(ceiling, tie_share)
            else:
                floor = max(floor, tie_share)
    return floor, ceiling


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
        return {target: -np.log1p(-u) for target, u in clipped.items()}
    return {target: gammaincinv(alpha, u) for target, u in clipped.items()}


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


def gammas_to_row_by_district(
    gammas: Mapping[Destination, np.ndarray],
    ordered_targets: Sequence[Destination],
    ranks: np.ndarray,
    free_targets: Sequence[Destination] = (),
) -> dict[Destination, np.ndarray]:
    """`gammas_to_row` quand l'ordre de préférence varie d'une circonscription à
    l'autre (voir `extension_ranks`).

    Le classement des parts est identique — c'est toujours la i-ème plus grande
    part qui va à la i-ème destination préférée — mais « la i-ème préférée » n'est
    plus la même partout : chaque circonscription lit `ranked` à son propre rang.
    """
    targets = list(ordered_targets) + list(free_targets)
    values = np.array([gammas[target] for target in targets])
    shares = values / values.sum(axis=0)

    n_ordered = len(ordered_targets)
    ranked = -np.sort(-shares[:n_ordered], axis=0)
    districts = np.arange(shares.shape[1])
    row = {
        target: ranked[ranks[i], districts] for i, target in enumerate(ordered_targets)
    }
    row.update({target: shares[n_ordered + j] for j, target in enumerate(free_targets)})
    return row
