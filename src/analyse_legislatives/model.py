from dataclasses import dataclass
from collections import Counter
import numpy as np
from analyse_legislatives.circonscription import (
    CirconscriptionPrediction,
    CirconscriptionResult,
)
from scipy.stats import truncnorm

from analyse_legislatives.utils import PoliticalFamily

SECOND_ROUND_PARTIES = list(PoliticalFamily.__members__.values()) + ["ABS"]


@dataclass(frozen=True)
class StatisticalModelParameters:
    parameters: dict

    def to_matrix(self, order=None) -> np.ndarray:
        """
        Returns a 6x6 matrix
        """
        if order is None:
            order = [
                PoliticalFamily.DIV,
                PoliticalFamily.ENSx,
                PoliticalFamily.LRx,
                PoliticalFamily.NFPx,
                PoliticalFamily.RNx,
                "ABS",
            ]
        return np.array(
            [
                [
                    (
                        self.parameters[first_party].get(second_party, 0)
                        if first_party != second_party
                        else 0
                    )
                    for second_party in order
                ]
                for first_party in order
            ]
        )

    def to_dict(self, parameters_matrix: np.ndarray, order: list = None) -> dict:
        if order is None:
            order = [
                PoliticalFamily.DIV,
                PoliticalFamily.ENSx,
                PoliticalFamily.LRx,
                PoliticalFamily.NFPx,
                PoliticalFamily.RNx,
                "ABS",
            ]
        parameters = {}
        for i, party in enumerate(order):
            parameters[party] = {
                second_party: parameters_matrix[i, j]
                for j, second_party in enumerate(order)
            }

        return parameters

    @classmethod
    def _sample_from_truncated_gaussian(cls, hyperparameters, variance: float):
        sampled_parameters = {}
        for source_party, other_parties in hyperparameters.items():
            sampled_parameters_source_party = {}
            for target_party, param in other_parties.items():
                sampled_parameters_source_party[target_party] = truncnorm.rvs(
                    a=-param / variance,
                    b=(1 - param) / variance,
                    loc=param,
                    scale=variance,
                )  # Parameters must be between 0 and 1
            sampled_parameters[source_party] = sampled_parameters_source_party

        return cls(sampled_parameters)

    def normalize(self, district_result: CirconscriptionResult):
        second_round_mask = (
            np.array(list(district_result.competing_parties_results.values())) > 0
        ).astype(int)
        second_round_mask[-1] = 1  # Abstentions
        full_binary_mask = np.tile(second_round_mask, (6, 1))
        parameters_for_circo = (
            (1 - full_binary_mask.T)
            * self.to_matrix(district_result.competing_parties_results.keys())
            * full_binary_mask
        )

        return StatisticalModelParameters(
            self.to_dict(
                np.nan_to_num(
                    parameters_for_circo / parameters_for_circo.sum(1)[:, None], 0
                ),
                order=district_result.competing_parties_results.keys(),
            )
        )


@dataclass
class StatisticalModel:
    hyperparameters: StatisticalModelParameters
    variance: float = 0.2
    fixed_parameters: bool = False

    def __post_init__(self):
        if not self.fixed_parameters:
            self.parameters = (
                StatisticalModelParameters._sample_from_truncated_gaussian(
                    self.hyperparameters.parameters, self.variance
                )
            )
        else:
            self.parameters = self.hyperparameters

    def sample_transfers_in_circonscription(
        self, circonscription_details: CirconscriptionResult
    ):
        normalized_parameters_for_circo = self.parameters.normalize(
            circonscription_details
        )

        transfers = {}
        for (
            eliminated_party,
            votes_pool_party,
        ) in circonscription_details.available_vote_pools_by_party().items():
            target_parties = list(
                normalized_parameters_for_circo.parameters[eliminated_party].keys()
            )

            transfers[eliminated_party] = {
                target_parties[i]: transferred_votes
                for i, transferred_votes in enumerate(
                    np.random.multinomial(
                        n=votes_pool_party,
                        pvals=list(
                            normalized_parameters_for_circo.parameters[
                                eliminated_party
                            ].values()
                        ),
                    )
                )
            }
        return transfers

    def predict_circonscription(
        self, circonscription_details: CirconscriptionResult
    ) -> CirconscriptionPrediction:
        predicted_vote_transfers = self.sample_transfers_in_circonscription(
            circonscription_details
        )
        votes_round_one = circonscription_details.competing_parties_results
        agregated_vote_transfers = {
            party: sum(
                predicted_vote_transfers[source_party].get(party, 0)
                for source_party in predicted_vote_transfers.keys()
            )
            for party in SECOND_ROUND_PARTIES
        }
        return CirconscriptionPrediction(
            circonscription_details.circonscription,
            {
                party: agregated_vote_transfers[party] + votes_round_one[party]
                for party in SECOND_ROUND_PARTIES
            },
        )

    def predict_all_circonscriptions(
        self, all_circonscription_details: list[CirconscriptionResult]
    ) -> list[CirconscriptionPrediction]:
        return [
            self.predict_circonscription(circonscription_details)
            for circonscription_details in all_circonscription_details
        ]
