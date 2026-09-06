"""Modèles de référence déterministes, sans aucun report de voix.

Un modèle probabiliste ne se juge pas dans l'absolu : un energy score de 15,6
sièges ne veut rien dire tant qu'on ignore ce que produit la règle la plus bête
possible. Le point de comparaison retenu ici est celui que n'importe qui peut
appliquer sans modèle : **le candidat qualifié arrivé en tête au premier tour
gagne le second**.

Cette règle ignore tout ce que le billet passe son temps à modéliser — reports,
désistements, démobilisation, remobilisation des non-exprimés. Elle donne donc
la part du résultat qui était déjà acquise au soir du premier tour, et le reste
mesure ce que les reports ajoutent réellement.

La prévision est **déterministe** : un unique vecteur de sièges, sans
incertitude. C'est ce qui la rend comparable aux modèles simulés sans traitement
particulier — l'energy score d'une masse de Dirac se réduit à la distance
euclidienne à la vérité (le terme de dispersion est nul), c'est-à-dire
exactement la colonne « scénario médian seul » déjà imprimée par
`scripts/evaluate.py`.
"""

from collections.abc import Mapping, Sequence

import numpy as np

from analyse_legislatives.circonscription import CirconscriptionResult
from analyse_legislatives.parties import FAMILIES

NO_WINNER = -1
"""Circonscription sans candidat qualifié : aucune famille ne peut être désignée."""


def first_round_leader_winners(
    districts: Sequence[CirconscriptionResult],
) -> np.ndarray:
    """Indice de la famille en tête au premier tour PARMI LES QUALIFIÉS.

    Ce sont les voix des candidats qualifiés qui départagent, pas le total de la
    famille dans la circonscription : les voix d'un candidat éliminé de la même
    famille appartiennent au réservoir de reports, dont la règle de référence ne
    veut précisément rien savoir.

    Les ex æquo sont tranchés par l'ordre canonique de `FAMILIES`, comme
    `argmax` le fait dans `projections.winners_by_simulation` — le cas n'existe
    pas dans les données 2024.
    """
    votes = np.array(
        [
            [district.competing_parties_results.get(family, 0) for family in FAMILIES]
            for district in districts
        ],
        dtype=float,
    )
    winners = votes.argmax(axis=1)
    return np.where(votes.max(axis=1) > 0, winners, NO_WINNER)


def first_round_leader_seats(
    districts: Sequence[CirconscriptionResult],
    first_round_seats: Mapping[str, int] | None = None,
) -> np.ndarray:
    """Vecteur de sièges de la règle de référence, dans l'ordre de `FAMILIES`.

    `first_round_seats` ajoute les circonscriptions déjà pourvues au premier
    tour, exactement comme le fait `scripts/evaluate.py` pour les modèles : sans
    elles, les deux totaux ne porteraient pas sur la même assemblée.
    """
    winners = first_round_leader_winners(districts)
    seats = np.array(
        [np.count_nonzero(winners == k) for k in range(len(FAMILIES))], dtype=float
    )
    if first_round_seats:
        seats += np.array(
            [first_round_seats.get(str(family), 0) for family in FAMILIES], dtype=float
        )
    return seats
