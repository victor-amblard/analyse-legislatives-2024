"""Models anchored on valid votes as a share of registered voters."""

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.special import expit, logit
from scipy.stats import norm

from analyse_legislatives.circonscription import CirconscriptionResult
from analyse_legislatives.models.base import (
    DistrictRows,
    Model,
    SimulationParameters,
)
from analyse_legislatives.models.kernel import KernelModel
from analyse_legislatives.models.national import NationalModel
from analyse_legislatives.parties import NON_EXPRIMES
from analyse_legislatives.transfers import TransferMatrix, normalize_for_district

Z90 = float(norm.ppf(0.95))


def _declared(value: float | None, name: str) -> float:
    """Rend non optionnelle une croyance que `__post_init__` a déjà validée.

    Ces trois champs sont `float | None` DANS LA SIGNATURE parce qu'ils n'ont
    pas de défaut défendable : les omettre doit échouer bruyamment plutôt que
    faire tourner le modèle sur une valeur inventée. Une fois l'instance
    construite, ils ne sont plus jamais `None` — ce passage le dit au
    vérificateur de types plutôt que de le laisser deviner."""
    if value is None:
        raise ValueError(f"`{name}` doit être déclaré.")
    return value


@dataclass
class ExpressedShareAnchoredMixin(Model):
    """Ancre chaque circonscription sur sa part de suffrages exprimés du 1er tour.

    Un changement national et une déviation locale sont tirés sur l'échelle logit.
    La rétention des non-exprimés est ensuite DÉTERMINÉE par comptabilité, au lieu
    d'être tirée.

    C'est la « variante plus souple » annoncée par l'HYPOTHÈSE 4 du billet
    (`writeup.fr.md`) : la mobilisation cesse d'être une proportion libre du
    réservoir pour devenir ce qu'il faut afin d'atteindre une part de suffrages
    exprimés visée. La forme de la répartition entre qualifiés, elle, reste celle
    de `transfers._non_expressed_row`.
    """

    national_expressed_band_pts: float | None = None
    district_expressed_band_pts: float | None = None
    expected_expressed_change_pts: float | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        bands = (self.national_expressed_band_pts, self.district_expressed_band_pts)
        if any(value is None or not 0 < value < 50 for value in bands):
            raise ValueError(
                "Expressed-share bands must be declared in (0, 50) points."
            )
        change = self.expected_expressed_change_pts
        if change is None or not -50 < change < 50:
            raise ValueError(
                "Expected expressed-share change must be declared in (-50, 50)."
            )

    @staticmethod
    def _first_round_expressed_share(
        district: CirconscriptionResult,
    ) -> tuple[float, float]:
        expressed = sum(district.competing_parties_results.values()) + sum(
            district.eliminated_parties_results.values()
        )
        registered = expressed + district.non_expressed
        if registered == 0:
            return 0.0, 0.0
        return expressed / registered, float(registered)

    @staticmethod
    def _sigma(points: float, anchor: float) -> float:
        """Convert a symmetric 90% band in points to the logit scale."""
        anchor_logit = logit(anchor)
        distances = (
            abs(logit(anchor - points / 100) - anchor_logit),
            abs(logit(anchor + points / 100) - anchor_logit),
        )
        return float(min(distances) / Z90)

    @staticmethod
    def _solve_levers(
        target_expressed_share: float,
        first_round_expressed_share: float,
        demobilised_share: float,
        qualified_share: float,
        baseline_demobilisation: float,
    ) -> tuple[float, float]:
        """
        `(rétention des non-exprimés, rétention propre des qualifiés)` réalisant
        la part de suffrages exprimés visée, par comptabilité exacte.

            tau = t1 - d - (1 - rho) q + (1 - r) (1 - t1)

        `d` est ce que les réservoirs éliminés renvoient aux non-exprimés, `q` la
        part d'inscrits réunie par les LIGNES gouvernées par `rho`, `rho` la
        probabilité qu'un de leurs électeurs revienne voter, `r` la rétention des
        non-exprimés.

        `q` compte les voix propres des qualifiés et celles des éliminés de leur
        famille, qui passent par la même ligne de report.

        `baseline_demobilisation` est tiré une fois au niveau national. Il fixe
        une démobilisation minimale strictement positive, y compris lorsque des
        non-exprimés du premier tour se mobilisent en sens inverse. Si cette
        démobilisation ne suffit pas à atteindre une cible très basse, elle est
        augmentée juste assez ; la mobilisation reste alors nulle.

        `rho` est le même pour tous les qualifiés de la circonscription : rien ne
        dit lequel des deux finalistes démobilise le plus, et le supposer serait
        ajouter une croyance qu'on ne sait pas défendre.
        """
        reservoir = 1.0 - first_round_expressed_share
        floor = (
            first_round_expressed_share
            - demobilised_share
            - baseline_demobilisation * qualified_share
        )

        if target_expressed_share >= floor:
            if reservoir <= 0:
                return 1.0, 1.0 - baseline_demobilisation
            mobilised = (target_expressed_share - floor) / reservoir
            return (
                float(np.clip(1.0 - mobilised, 0.0, 1.0)),
                1.0 - baseline_demobilisation,
            )

        if qualified_share <= 0:
            return 1.0, 1.0
        own = (
            1.0
            - baseline_demobilisation
            - (floor - target_expressed_share) / qualified_share
        )
        return 1.0, float(np.clip(own, 0.0, 1.0))

    def _demobilised_share(
        self,
        matrix: TransferMatrix,
        district: CirconscriptionResult,
        registered: float,
    ) -> float:
        if registered == 0:
            return 0.0
        non_expressed_tilt = sum(self.non_expressed_tilt_bounds) / 2
        normalized = normalize_for_district(matrix, district, non_expressed_tilt)
        lost = sum(
            votes * normalized.rates.get(party, {}).get(NON_EXPRIMES, 0.0)
            for party, votes in district.eliminated_parties_results.items()
            if district.competing_parties_results.get(party, 0) <= 0
        )
        return float(lost / registered)

    def _complete_matrices(
        self,
        rows_per_district: Sequence[DistrictRows],
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> list[TransferMatrix]:
        """
        Étape 3, redéfinie : au lieu de LIRE la rétention des non-exprimés dans le
        prior, on la RÉSOUT — avec la rétention propre des qualifiés — pour que la
        part de suffrages exprimés de chaque circonscription atteigne une cible
        tirée sur l'échelle logit.

        """
        if not districts:
            return []

        # Matrices provisoires, sans ligne de non-exprimés : `_demobilised_share`
        # ne lit que les lignes des partis éliminés.
        provisional = [TransferMatrix(rows) for rows in rows_per_district]

        first_shares, registered = zip(
            *(self._first_round_expressed_share(district) for district in districts)
        )
        shares = np.asarray(first_shares)
        weights = np.asarray(registered)
        if weights.sum() == 0:
            return super()._complete_matrices(rows_per_district, districts, draw)

        national = float(weights @ shares / weights.sum())
        centre = (
            national
            + _declared(
                self.expected_expressed_change_pts, "expected_expressed_change_pts"
            )
            / 100
        )
        if not 0 < national < 1 or not 0 < centre < 1:
            return super()._complete_matrices(rows_per_district, districts, draw)

        national_sigma = self._sigma(
            _declared(self.national_expressed_band_pts, "national_expressed_band_pts"),
            centre,
        )
        district_sigma = self._sigma(
            _declared(self.district_expressed_band_pts, "district_expressed_band_pts"),
            centre,
        )
        national_change = logit(centre) - logit(national)
        national_change += float(self.rng.normal(0, national_sigma))

        local_change = self.rng.standard_normal(len(districts))
        local_change -= weights @ local_change / weights.sum()

        # Coeur du modèle logit(r_{c,2}) = logit(r_{c,1}) + delta_nat + delta_c
        targets = expit(logit(shares) + national_change + district_sigma * local_change)
        baseline_demobilisation = draw.qualified_demobilisation

        contexts = []
        for matrix, district, first_share, n_registered in zip(
            provisional, districts, shares, registered
        ):
            governed = {
                party: votes + district.eliminated_parties_results.get(party, 0)
                for party, votes in district.competing_parties_results.items()
                if votes > 0
            }
            qualified_share = (
                sum(governed.values()) / n_registered if n_registered else 0.0
            )
            eliminated_demobilised = self._demobilised_share(
                matrix, district, n_registered
            )
            minimum = first_share - eliminated_demobilised - qualified_share
            maximum = (
                first_share
                - eliminated_demobilised
                - baseline_demobilisation * qualified_share
                + 1.0
                - first_share
            )
            contexts.append(
                (governed, qualified_share, eliminated_demobilised, minimum, maximum)
            )

        # Le logit décrit une cible latente, mais les deux réservoirs disponibles
        # imposent des bornes physiques. Les appliquer ici évite que `_solve_levers`
        # masque une cible impossible en bornant silencieusement une probabilité.
        targets = np.array(
            [
                np.clip(target, minimum, maximum)
                for target, (*_, minimum, maximum) in zip(targets, contexts)
            ]
        )

        anchored = []
        for rows, district, target, first_share, n_registered, context in zip(
            rows_per_district, districts, targets, shares, registered, contexts
        ):
            # Les voix gouvernées par `rho` : celles des qualifiés, plus celles
            # des éliminés de leur propre famille — `normalize_for_district` leur
            # donne la même ligne, et `_demobilised_share` les exclut donc de `d`.
            governed, qualified_share, eliminated_demobilised, _, _ = context
            retention, own_retention = self._solve_levers(
                float(target),
                float(first_share),
                eliminated_demobilised,
                qualified_share,
                baseline_demobilisation,
            )
            anchored.append(
                TransferMatrix(
                    rows | {NON_EXPRIMES: {NON_EXPRIMES: retention}},
                    own_retentions={party: own_retention for party in governed},
                )
            )
        return anchored


@dataclass
class NationalAnchoredModel(ExpressedShareAnchoredMixin, NationalModel):
    """National transfer model with district expressed-share anchoring."""


@dataclass
class KernelAnchoredModel(ExpressedShareAnchoredMixin, KernelModel):
    """Kernel transfer model with district expressed-share anchoring."""
