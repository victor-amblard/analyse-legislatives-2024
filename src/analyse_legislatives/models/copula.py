"""
Étape 2 pour toutes les variantes : des uniformes vers des lignes de report.

Le partage de responsabilité tient en deux phrases :

- **la sous-classe** produit, pour une cellule, un vecteur d'uniformes U(0,1) —
  une par circonscription. C'est là, et seulement là, que vit la structure de
  corrélation entre circonscriptions (aucune pour `NationalModel`, un noyau
  gaussien pour `KernelModel`) ;
- **cette classe** transforme ces uniformes en lignes de taux respectant l'ordre
  de préférence, via les fonctions pures de `models.ordinal`.

Travailler en uniformes est ce qui rend la séparation possible : une uniforme
transportée par une fonction quantile garde sa copule, donc la sous-classe décide
de la dépendance sans rien savoir de la transformation appliquée ensuite.
"""

from abc import abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from analyse_legislatives.circonscription import CirconscriptionResult
from analyse_legislatives.parties import Destination
from analyse_legislatives.models.base import (
    Model,
    SimulationParameters,
    TransferRow,
)
from analyse_legislatives.models.ordinal import gammas_to_row, uniforms_to_gammas


@dataclass
class CopulaModel(Model):
    """Ordonne chaque ligne à partir d'uniformes fournies par la sous-classe."""

    def _begin_simulation(
        self,
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> None:
        """Point d'accroche pour préparer l'état partagé par toutes les lignes
        d'une même simulation — la décomposition de Cholesky du noyau, par
        exemple. Appelé une fois, avant toute ligne. Sans effet ici."""

    @abstractmethod
    def _sample_row_uniforms(
        self,
        targets: Sequence[Destination],
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> Mapping[Destination, np.ndarray]:
        """Un tableau d'uniformes U(0,1) de forme `(n_circonscriptions,)` par
        cellule de la ligne. `targets` est la liste des destinations, dans l'ordre
        de préférence tiré pour cette simulation."""

    def _sample_rows_per_district(
        self,
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> list[dict[Destination, TransferRow]]:
        n = len(districts)
        self._begin_simulation(districts, draw)

        rows_per_district: list[dict[Destination, TransferRow]] = [{} for _ in range(n)]
        for source_party, extension in draw.extensions.items():
            # Les destinations libres reçoivent aussi une uniforme : elles
            # participent à la normalisation de la ligne, seul leur RANG échappe à
            # l'ordre de préférence.
            free = self.free_targets_for(source_party)
            targets = list(extension) + free

            uniforms = self._sample_row_uniforms(targets, districts, draw)
            row = gammas_to_row(
                uniforms_to_gammas(uniforms, draw.alpha), extension, free
            )

            # Les variantes nationales ne produisent qu'une valeur par cellule,
            # partagée par toutes les circonscriptions : on la diffuse ici plutôt
            # que d'imposer aux sous-classes de la répliquer elles-mêmes.
            per_cell = {
                target: np.broadcast_to(values, (n,)) for target, values in row.items()
            }
            for i in range(n):
                rows_per_district[i][source_party] = {
                    target: float(values[i]) for target, values in per_cell.items()
                }
        return rows_per_district
