"""Variante minimale : une seule matrice de report par simulation."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from analyse_legislatives.circonscription import CirconscriptionResult
from analyse_legislatives.parties import Destination
from analyse_legislatives.models.base import SimulationParameters
from analyse_legislatives.models.copula import CopulaModel


@dataclass
class NationalModel(CopulaModel):
    """
    Un seul jeu de taux de report par simulation, partagé à l'identique par toutes
    les circonscriptions. Aucune variation locale, donc aucune corrélation à
    modéliser — c'est le point de comparaison de référence pour mesurer ce
    qu'apportent réellement les mécanismes plus riches.

    C'est l'HYPOTHÈSE 5 du billet (`writeup.fr.md`), « absence de variations
    locales », que `KernelModel` relâche.
    """

    def _sample_row_uniforms(
        self,
        targets: Sequence[Destination],
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> Mapping[Destination, np.ndarray]:
        # Une seule uniforme par cellule ; `CopulaModel` la diffuse ensuite sur
        # les n circonscriptions.
        return {target: self.rng.random(1) for target in targets}
