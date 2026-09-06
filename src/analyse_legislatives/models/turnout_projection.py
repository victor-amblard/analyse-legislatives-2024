"""Projection entropique des flux de suffrages non exprimés.

Vocabulaire de ce module : un RÉSERVOIR est un ensemble de voix du premier tour
gouverné par une même ligne de report — les non-exprimés, les voix propres d'un
qualifié, celles d'une famille éliminée. Son TAUX est la probabilité qu'une de
ces voix finisse non exprimée au second tour. Toute la mécanique consiste à
déplacer ces taux le moins possible pour atteindre un nombre de voix non
exprimées visé.
"""

from collections.abc import Mapping, Sequence

import numpy as np
from scipy.optimize import brentq
from scipy.special import expit, logit

from analyse_legislatives.models.ordinal import bounds_for_target
from analyse_legislatives.parties import NON_EXPRIMES, Destination


def restricted_non_expressed_probability(
    row: Mapping[Destination, float], available: set[Destination]
) -> float:
    """Taux de non-expression d'une ligne, restreinte au bulletin local."""
    available_mass = sum(row.get(target, 0.0) for target in available)
    return float(row.get(NON_EXPRIMES, 0.0) / available_mass) if available_mass else 0.0


def ordinal_bounds_from_order_constraint(
    row: Mapping[Destination, float],
    tiers: Sequence[Sequence[Destination]],
    available: set[Destination],
) -> tuple[float, float]:
    """Taux plancher et plafond, une fois la ligne restreinte au bulletin local.

    La contrainte d'ordre elle-même vit dans `ordinal.bounds_for_target`, aux
    côtés de la construction qu'elle contraint. Ne reste ici que le passage de
    la ligne brute à la ligne restreinte : la restriction renormalise, donc
    déplace les parts, et les bornes avec elles.
    """
    raw_floor, raw_ceiling = bounds_for_target(row, tiers, NON_EXPRIMES)

    raw_share = float(row[NON_EXPRIMES])
    expressed_mass = 1.0 - raw_share
    if expressed_mass <= 0:
        return 1.0, 1.0

    available_expressed_mass = sum(
        row.get(target, 0.0) for target in available if target != NON_EXPRIMES
    )

    def restrict(raw_bound: float) -> float:
        if raw_bound <= 0:
            return 0.0
        if raw_bound >= 1:
            return 1.0
        scaled_expressed_mass = (
            available_expressed_mass * (1.0 - raw_bound) / expressed_mass
        )
        return float(raw_bound / (raw_bound + scaled_expressed_mass))

    return restrict(raw_floor), restrict(raw_ceiling)


def project_probabilities(
    drawn_rates: Sequence[float],
    reservoir_votes: Sequence[float],
    target_non_expressed: float,
    lowest_rates: Sequence[float],
    highest_rates: Sequence[float],
) -> np.ndarray:
    """Déplace les taux de non-expression jusqu'au total de voix visé.

    La solution minimise

    ``sum_i voix_i * KL(Bernoulli(taux_i) || Bernoulli(taux tiré_i))``

    sous ``sum_i voix_i * taux_i = total visé`` et les bornes ordinales. Hors
    borne, tous les logits reçoivent le même décalage de Lagrange. Le problème
    est donc ramené à la recherche d'une seule racine monotone.
    """
    drawn = np.asarray(drawn_rates, dtype=float)
    votes = np.asarray(reservoir_votes, dtype=float)
    lowest = np.asarray(lowest_rates, dtype=float)
    highest = np.asarray(highest_rates, dtype=float)
    if not (drawn.shape == votes.shape == lowest.shape == highest.shape):
        raise ValueError("Les taux, voix et bornes doivent avoir même taille.")
    if np.any(votes < 0) or np.any(lowest > highest):
        raise ValueError("Voix négatives ou bornes de projection incohérentes.")
    if np.any(drawn < lowest - 1e-12) or np.any(drawn > highest + 1e-12):
        raise ValueError("Le tirage initial ne respecte pas ses bornes ordinales.")

    fewest_votes = float(votes @ lowest)
    most_votes = float(votes @ highest)
    # `min`/`max` et non `np.clip` : sur un scalaire, `np.clip` coûte un appel
    # ufunc complet pour le même résultat, et il est appelé une fois par
    # circonscription et par tirage.
    target_non_expressed = min(
        max(float(target_non_expressed), fewest_votes), most_votes
    )
    tolerance = 1e-12 * max(1.0, float(votes.sum()))
    if target_non_expressed <= fewest_votes + tolerance:
        return lowest.copy()
    if target_non_expressed >= most_votes - tolerance:
        return highest.copy()

    # Un réservoir tiré exactement à 0 ou à 1 ne peut plus bouger : le décalage
    # des logits n'a pas de prise sur lui.
    always_expresses = drawn <= 0
    never_expresses = drawn >= 1
    movable = ~(always_expresses | never_expresses)

    # `vote_gap` est évalué ~17 fois par résolution, sur des tableaux de 4 à 8
    # cases : le coût est presque entièrement de l'allocation et de l'appel
    # numpy, pas de l'arithmétique. Tout ce qui ne dépend pas du décalage sort
    # donc de la fermeture, et les tampons sont réutilisés d'une évaluation à
    # l'autre. Les valeurs calculées sont inchangées : mêmes entrées d'`expit`,
    # même `clip`, même produit scalaire sur le tableau entier.
    shifted = np.empty_like(drawn)
    rates = np.empty_like(drawn)
    clipped = np.empty_like(drawn)

    if movable.all():
        # Cas courant : aucun réservoir figé, donc aucun masque à appliquer.
        drawn_logits = logit(drawn)

        def rates_at(logit_shift: float) -> np.ndarray:
            np.add(drawn_logits, logit_shift, out=shifted)
            expit(shifted, out=rates)
            return np.clip(rates, lowest, highest, out=clipped)

    else:
        # Les cases figées ne dépendent pas du décalage : on les écrit une fois.
        rates[always_expresses] = 0.0
        rates[never_expresses] = 1.0
        movable_logits = logit(drawn[movable])
        movable_shifted = np.empty_like(movable_logits)

        def rates_at(logit_shift: float) -> np.ndarray:
            np.add(movable_logits, logit_shift, out=movable_shifted)
            rates[movable] = expit(movable_shifted)
            return np.clip(rates, lowest, highest, out=clipped)

    def vote_gap(logit_shift: float) -> float:
        return float(votes @ rates_at(logit_shift) - target_non_expressed)

    logit_shift = brentq(vote_gap, -1_000.0, 1_000.0, xtol=1e-13, rtol=1e-13)
    # `clipped` est un tampon réutilisé : le rendre tel quel exposerait un
    # tableau que la prochaine projection écraserait.
    return rates_at(logit_shift).copy()



BISECTION_STEPS = 100
"""Itérations de la bissection groupée.

Le décalage vit dans [-1000, 1000] : 100 dichotomies le localisent à 2e-27,
très en deçà de la précision utile. C'est `expit` qui limite ensuite, pas la
recherche de racine — d'où l'accord à ~1e-15 avec `brentq`.
"""


def project_probabilities_batch(
    drawn_rates: np.ndarray,
    reservoir_votes: np.ndarray,
    targets: np.ndarray,
    lowest_rates: np.ndarray,
    highest_rates: np.ndarray,
) -> np.ndarray:
    """`project_probabilities` pour toutes les circonscriptions à la fois.

    Chaque ligne est une circonscription, chaque colonne un réservoir ; les
    colonnes en trop sont remplies avec ``votes = 0``, ce qui les rend
    silencieuses dans la contrainte comptable.

    Pourquoi grouper : la version scalaire lance une résolution `brentq` par
    circonscription ET par tirage, soit 501 racines dont chacune rappelle du
    Python une quinzaine de fois sur des tableaux de 4 à 8 cases. Le coût est
    presque entièrement de l'appel, pas du calcul. Une bissection commune —
    licite parce que la contrainte est monotone en le décalage, et que chaque
    ligne a sa propre racine — remplace 501 recherches par une centaine
    d'opérations vectorielles.

    L'écart avec `brentq` est de l'ordre de 1e-15 par taux : les deux résolvent
    la même équation, avec un critère d'arrêt différent.
    """
    drawn = np.asarray(drawn_rates, dtype=float)
    votes = np.asarray(reservoir_votes, dtype=float)
    lowest = np.asarray(lowest_rates, dtype=float)
    highest = np.asarray(highest_rates, dtype=float)
    targets = np.asarray(targets, dtype=float)
    if not (drawn.shape == votes.shape == lowest.shape == highest.shape):
        raise ValueError("Les taux, voix et bornes doivent avoir même forme.")
    if drawn.ndim != 2 or targets.shape != (drawn.shape[0],):
        raise ValueError("Attendu des tableaux (circonscriptions, réservoirs).")
    if np.any(votes < 0) or np.any(lowest > highest):
        raise ValueError("Voix négatives ou bornes de projection incohérentes.")

    fewest = (votes * lowest).sum(axis=1)
    most = (votes * highest).sum(axis=1)
    targets = np.clip(targets, fewest, most)
    tolerance = 1e-12 * np.maximum(1.0, votes.sum(axis=1))

    # `logit` renvoie -inf en 0 et +inf en 1 : le décalage n'a alors aucune
    # prise et `expit` restitue exactement 0 et 1. Les réservoirs figés se
    # traitent donc tout seuls, sans masque.
    with np.errstate(divide="ignore"):
        drawn_logits = logit(drawn)

    low_shift = np.full(drawn.shape[0], -1_000.0)
    high_shift = np.full(drawn.shape[0], 1_000.0)
    for _ in range(BISECTION_STEPS):
        middle = 0.5 * (low_shift + high_shift)
        rates = np.clip(expit(drawn_logits + middle[:, None]), lowest, highest)
        below = (votes * rates).sum(axis=1) < targets
        low_shift = np.where(below, middle, low_shift)
        high_shift = np.where(below, high_shift, middle)

    middle = 0.5 * (low_shift + high_shift)
    projected = np.clip(expit(drawn_logits + middle[:, None]), lowest, highest)

    # Les cibles hors d'atteinte sont rabattues sur la borne, comme le fait la
    # version scalaire avant même de chercher une racine.
    at_floor = targets <= fewest + tolerance
    at_ceiling = targets >= most - tolerance
    projected = np.where(at_floor[:, None], lowest, projected)
    return np.where(at_ceiling[:, None], highest, projected)


def set_restricted_non_expressed_probability(
    row: Mapping[Destination, float],
    available: set[Destination],
    wanted_rate: float,
) -> dict[Destination, float]:
    """Modifie une ligne brute pour obtenir le taux local demandé.

    La transformation est un tilt exponentiel de la cellule ``NON_EXPRIMES``.
    Toutes les autres cellules reçoivent le même facteur, ce qui préserve leur
    somme, leurs rapports et donc leur ordre.
    """
    adjusted = {target: float(value) for target, value in row.items()}
    raw_share = float(adjusted[NON_EXPRIMES])
    current_rate = restricted_non_expressed_probability(adjusted, available)

    if wanted_rate <= 0:
        new_raw_share = 0.0
    elif wanted_rate >= 1:
        new_raw_share = 1.0
    elif current_rate <= 0 or current_rate >= 1 or raw_share <= 0 or raw_share >= 1:
        raise ValueError("Une probabilité située sur le bord ne peut pas être déplacée.")
    else:
        logit_shift = float(logit(wanted_rate) - logit(current_rate))
        new_raw_share = float(expit(logit(raw_share) + logit_shift))

    expressed_scale = (1.0 - new_raw_share) / (1.0 - raw_share) if raw_share < 1 else 0.0
    for target in adjusted:
        if target != NON_EXPRIMES:
            adjusted[target] *= expressed_scale
    adjusted[NON_EXPRIMES] = new_raw_share
    return adjusted
