"""Circonscriptions, résultats du 1er tour et prédictions du 2nd."""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from analyse_legislatives.parties import (
    NON_EXPRIMES,
    Destination,
)


@dataclass(frozen=True)
class Circonscription:
    id: str
    name: str

    @classmethod
    def init_from_insee(cls, insee_id, name):
        id = (
            insee_id[:2] + insee_id[3:]
            if (
                insee_id[2] == "0"
                and (not insee_id[1].isnumeric() or int(insee_id[:2]) <= 95)
            )  # Soit Corse, soit 2 chiffres pour le département
            else insee_id
        )
        return cls(id, name)

    def is_overseas(self):
        return len(self.id) > 4


@dataclass(frozen=True)
class CirconscriptionResult:
    circonscription: Circonscription
    competing_parties_results: Mapping[Destination, int]
    """Voix du 1er tour des partis qualifiés pour le 2nd. Les clés couvrent
    toujours l'ordre canonique complet (`DESTINATIONS`), à zéro pour les partis
    non qualifiés — c'est ce qui rend l'indexation des matrices non ambiguë."""

    eliminated_parties_results: Mapping[Destination, int]
    non_expressed: int

    def available_vote_pools_by_party(self) -> dict[Destination, int]:
        """
        TOUTES les voix du 1er tour, rangées par la ligne de matrice qui les
        gouverne : réservoirs éliminés, voix propres des qualifiés, non-exprimés.

        Les voix des qualifiés passent par la matrice comme les autres, au lieu
        d'être ajoutées telles quelles au résultat. C'est ce qui rend leur
        rétention pilotable : leur ligne vaut `rho` sur eux-mêmes et `1 - rho`
        vers les non-exprimés (voir `normalize_for_district`), là où les ajouter
        hors matrice revenait à imposer `rho = 1` sans le dire.

        Les deux réservoirs sont ADDITIONNÉS et non fusionnés : une famille peut
        avoir deux candidats dans la circonscription, dont un seul qualifié, et
        `dict | dict` ferait alors disparaître les voix de l'éliminé. Les deux
        parts sont gouvernées par la même ligne, donc les sommer est exact.
        """
        pools = {
            party: self.eliminated_parties_results.get(party, 0)
            + self.competing_parties_results.get(party, 0)
            # `{**a, **b}` et NON `a.keys() | b.keys()` : l'union d'ensembles
            # perd l'ordre d'insertion, et cet ordre gouverne la séquence des
            # tirages multinomiaux dans `sample_transfers_in_circonscription`.
            # Le changer change les résultats à seed fixée.
            for party in {
                **self.eliminated_parties_results,
                **self.competing_parties_results,
            }
        }
        return {**pools, NON_EXPRIMES: self.non_expressed}

    def n_competing(self) -> int:
        """Nombre de partis effectivement qualifiés (duel = 2, triangulaire = 3,
        quadrangulaire = 4)."""
        return sum(1 for votes in self.competing_parties_results.values() if votes > 0)

    def __str__(self) -> str:
        s = "Résultats 1er tour\n"
        s += f"=== {self.circonscription.name} ({self.circonscription.id}) ===\n"
        s += "Partis en lice\n"
        s += "\n".join(
            [
                f"{source} : {votes}"
                for source, votes in self.competing_parties_results.items()
                if votes != 0
            ]
        )
        s += "\nPartis éliminés\n"
        s += "\n".join(
            [
                f"{source} : {votes}"
                for source, votes in self.eliminated_parties_results.items()
                if votes != 0
            ]
        )

        return s


@dataclass
class CirconscriptionPrediction:
    circonscription: Circonscription
    results: Mapping[Destination, int]
    """Voix projetées du 2nd tour. Indexé sur `DESTINATIONS` en entier, non-exprimés
    compris : `simulation.run` lit chaque destination de l'ordre canonique."""

    def get_winner(self):
        contenders = {
            party: score
            for party, score in self.results.items()
            if party != NON_EXPRIMES
        }
        parties = list(contenders)
        return parties[int(np.argmax(list(contenders.values())))]

    def __str__(self):
        lines = [
            f"Résultats pour : {self.circonscription.name}",
            f"Vainqueur : {self.get_winner()}",
            "=============",
        ]
        lines += [f"{party}: {votes}" for party, votes in self.results.items()]
        return "\n".join(lines) + "\n"
