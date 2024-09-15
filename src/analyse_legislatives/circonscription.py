from collections import Counter
from dataclasses import dataclass

import numpy as np

from analyse_legislatives.utils import PoliticalFamily


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
    competing_parties_results: dict[PoliticalFamily, int]
    eliminated_parties_results: dict[PoliticalFamily, int]
    abstention: int

    def available_vote_pools_by_party(self):
        return self.eliminated_parties_results | {"ABS": self.abstention}


@dataclass
class CirconscriptionPrediction:
    circonscription: Circonscription
    results: dict[PoliticalFamily, int]

    def get_winner(self):
        valid_winners = {
            party: score for party, score in self.results.items() if party != "ABS"
        }
        ordered_parties = list(valid_winners.keys())
        most_votes_index = np.argmax(list(valid_winners.values()))

        return ordered_parties[most_votes_index]

    def get_seats(self):
        winner = self.get_winner()

        return {
            party: 1 if party == winner else 0
            for party in PoliticalFamily.__members__.values()
        }

    @staticmethod
    def agregate_by_party(full_predictions: list):
        count_seats = Counter()
        for predicted_result in full_predictions:
            count_seats.update(predicted_result.get_seats())

        return dict(count_seats)

    def __str__(self):
        s = "Résultats pour : " + self.circonscription.name + "\n"
        s += "Vainqueur : " + self.get_winner() + "\n"
        s += "=============\n"
        for party, results in self.results.items():
            s += party + ": " + str(results) + "\n"
        return s
