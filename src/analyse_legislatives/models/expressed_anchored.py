"""Models anchored on valid votes as a share of registered voters."""

from dataclasses import dataclass, field
from collections.abc import Mapping, Sequence
from typing import NamedTuple

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
from analyse_legislatives.parties import NON_EXPRIMES, Destination
from analyse_legislatives.transfers import TransferMatrix
from analyse_legislatives.models.turnout_projection import (
    ordinal_bounds_from_order_constraint,
    project_probabilities_batch,
    restricted_non_expressed_probability,
    set_restricted_non_expressed_probability,
)

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


class _Reservoir(NamedTuple):
    """Un bloc de voix du premier tour, et la marge dont dispose la projection.

    `owner` dit de quelle ligne il relève : `NON_EXPRIMES` pour le réservoir
    d'abstention, `None` pour la démobilisation commune des qualifiés — qui
    n'est la ligne d'aucun parti — et le parti éliminé sinon.

    `drawn_rate` est le taux de non-expression tiré a priori ; `lowest_rate` et
    `highest_rate` sont les bornes que lui laisse l'ordre partiel déclaré.
    """

    owner: Destination | None
    votes: float
    drawn_rate: float
    lowest_achievable_rate: float
    highest_achievable_rate: float


class _DistrictReservoirs(NamedTuple):
    """Tout ce dont la projection d'une circonscription a besoin.

    `governed_votes` et `on_ballot` voyagent avec les réservoirs parce que la
    reconstruction de la matrice en a besoin et qu'ils sont déjà calculés au
    moment de les recenser.
    """

    reservoirs: list[_Reservoir]
    governed_votes: dict[Destination, int]
    on_ballot: set[Destination]


@dataclass
class ExpressedShareAnchoredMixin(Model):
    """Ancre chaque circonscription sur sa part de suffrages exprimés du 1er tour.

    Un changement national et une déviation locale sont tirés sur l'échelle logit.
    Les flux vers les non-exprimés sont ensuite projetés conjointement pour
    atteindre la cible en s'écartant le moins possible du tirage initial au sens
    de la divergence de Kullback-Leibler.

    C'est la « variante plus souple » annoncée par l'HYPOTHÈSE 4 du billet
    (`writeup.fr.md`) : la mobilisation cesse d'être une proportion libre du
    réservoir pour devenir ce qu'il faut afin d'atteindre une part de suffrages
    exprimés visée. La forme de la répartition entre qualifiés, elle, reste celle
    de `transfers._non_expressed_row`.
    """

    national_expressed_band_pts: float | None = None
    district_expressed_band_pts: float | None = None
    expected_expressed_change_pts: float | None = None

    # Trace de la simulation en cours, sur le modèle des `_drawn_*` de
    # `KernelModel` : `delta_nat` et les `delta_c` sont tirés ICI et n'apparaissent
    # dans aucun retour, alors qu'ils font partie des paramètres dont
    # `scripts/analyses/parameter_influence.py` mesure l'influence. Les exposer
    # évite de rejouer le tirage à côté du modèle — donc de le rejouer FAUX.
    _drawn_national_change: float | None = field(default=None, init=False, repr=False)
    _drawn_local_changes: np.ndarray | None = field(
        default=None, init=False, repr=False
    )
    _drawn_expressed_targets: np.ndarray | None = field(
        default=None, init=False, repr=False
    )

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

    def _expressed_targets(
        self,
        districts: Sequence[CirconscriptionResult],
        shares: np.ndarray,
        weights: np.ndarray,
    ) -> np.ndarray | None:
        """Part de suffrages exprimés visée par circonscription, ou `None`.

        `None` signale une part nationale dégénérée, que l'ancrage ne sait pas
        traiter : l'appelant délègue alors au modèle non ancré. Le test précède
        tout tirage, pour qu'un repli ne consomme pas le générateur.

        L'ORDRE des deux tirages est significatif — choc national d'abord, champ
        local ensuite. L'inverser changerait toutes les simulations à graine
        égale sans rien changer au modèle.
        """
        national = np.average(shares, weights=weights)
        centre = (
            national
            + _declared(
                self.expected_expressed_change_pts, "expected_expressed_change_pts"
            )
            / 100
        )
        if not 0 < national < 1 or not 0 < centre < 1:
            return None

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

        # delta_c passe par la structure de dépendance du modèle : indépendant par
        # circonscription pour les variantes nationales, corrélé par le noyau pour
        # les variantes locales. Le choc national est déjà porté par
        # `national_change`, donc ce champ ne mélange PAS de composante commune —
        # sans quoi le choc national serait compté deux fois.
        local_change = self.local_shock_field(districts)
        local_change -= np.average(local_change, weights=weights)

        self._drawn_national_change = float(national_change)
        self._drawn_local_changes = district_sigma * local_change
        # Coeur du modèle logit(r_{c,2}) = logit(r_{c,1}) + delta_nat + delta_c
        return expit(logit(shares) + national_change + district_sigma * local_change)

    def _district_reservoirs(
        self,
        rows: DistrictRows,
        district: CirconscriptionResult,
        draw: SimulationParameters,
    ) -> _DistrictReservoirs:
        """Recense les réservoirs pouvant alimenter les non-exprimés.

        Les deux premiers sont des leviers du tirage global — rétention des
        non-exprimés, démobilisation des qualifiés — et ne sont bornés que par
        [0, 1] : aucun ordre de préférence ne les contraint. Les suivants sont
        des lignes de report, donc bornés par l'ordre partiel déclaré.
        """
        on_ballot = {
            party
            for party, votes in district.competing_parties_results.items()
            if votes > 0
        } | {NON_EXPRIMES}
        governed_votes = {
            party: votes + district.eliminated_parties_results.get(party, 0)
            for party, votes in district.competing_parties_results.items()
            if votes > 0
        }

        reservoirs = [
            _Reservoir(
                owner=NON_EXPRIMES,
                votes=float(district.non_expressed),
                drawn_rate=draw.non_expressed_retention,
                lowest_achievable_rate=0.0,
                highest_achievable_rate=1.0,
            )
        ]

        qualified_votes = float(sum(governed_votes.values()))
        if qualified_votes > 0:
            reservoirs.append(
                _Reservoir(
                    owner=None,
                    votes=qualified_votes,
                    drawn_rate=draw.qualified_demobilisation,
                    lowest_achievable_rate=0.0,
                    highest_achievable_rate=1.0,
                )
            )

        for eliminated, votes in district.eliminated_parties_results.items():
            # Un éliminé dont la famille reste qualifiée emprunte la ligne de
            # cette famille : il est déjà compté dans `governed_votes`.
            if votes <= 0 or district.competing_parties_results.get(eliminated, 0) > 0:
                continue
            row = rows[eliminated]
            drawn_rate = restricted_non_expressed_probability(row, on_ballot)
            lowest, highest = ordinal_bounds_from_order_constraint(
                row, self.transfer_orderings[eliminated], on_ballot
            )
            reservoirs.append(
                _Reservoir(
                    owner=eliminated,
                    votes=float(votes),
                    drawn_rate=drawn_rate,
                    lowest_achievable_rate=lowest,
                    highest_achievable_rate=highest,
                )
            )

        return _DistrictReservoirs(reservoirs, governed_votes, on_ballot)

    def _anchored_matrix(
        self,
        rows: DistrictRows,
        district_reservoirs: _DistrictReservoirs,
        draw: SimulationParameters,
        projected_rates: np.ndarray,
        registered_voters: float,
    ) -> tuple[TransferMatrix, float]:
        """Rebâtit la matrice d'une circonscription à partir de ses taux projetés.

        La projection elle-même n'a plus lieu ici : elle est résolue pour toutes
        les circonscriptions à la fois dans `_complete_matrices`, la recherche de
        racine par circonscription ayant dominé le temps de simulation.

        Renvoie aussi la part de suffrages exprimés RÉELLEMENT atteinte : elle
        s'écarte de la cible dès qu'une borne ordinale devient active, et mieux
        vaut la lire que la supposer (voir `_drawn_expressed_targets`).
        """
        reservoirs = district_reservoirs.reservoirs
        votes = np.array([reservoir.votes for reservoir in reservoirs], dtype=float)
        realised_expressed_share = 1.0 - float(
            votes @ projected_rates / registered_voters
        )

        adjusted_rows = {owner: dict(row) for owner, row in rows.items()}
        for reservoir, rate in zip(reservoirs, projected_rates):
            if reservoir.owner is None or reservoir.owner == NON_EXPRIMES:
                continue
            adjusted_rows[reservoir.owner] = set_restricted_non_expressed_probability(
                adjusted_rows[reservoir.owner],
                district_reservoirs.on_ballot,
                float(rate),
            )

        by_owner = {
            reservoir.owner: float(rate)
            for reservoir, rate in zip(reservoirs, projected_rates)
        }
        # `None` marque la démobilisation commune : absente quand la
        # circonscription n'a aucune voix gouvernée par un qualifié.
        demobilisation = by_owner.get(None, draw.qualified_demobilisation)
        matrix = TransferMatrix(
            {
                **adjusted_rows,
                NON_EXPRIMES: {NON_EXPRIMES: by_owner[NON_EXPRIMES]},
            },
            own_retentions=dict.fromkeys(
                district_reservoirs.governed_votes, 1.0 - demobilisation
            ),
        )
        return matrix, realised_expressed_share

    def _complete_matrices(
        self,
        rows_per_district: Sequence[DistrictRows],
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> list[TransferMatrix]:
        """
        Étape 3, redéfinie : projette conjointement tous les flux vers les
        non-exprimés afin d'atteindre une cible tirée sur l'échelle logit.

        Pour un réservoir ``i``, ``p_i`` est la probabilité tirée a priori de ne
        pas s'exprimer. On choisit les ``q_i`` qui minimisent la somme des
        ``poids_i * KL(Bernoulli(q_i) || Bernoulli(p_i))`` sous la contrainte
        comptable sur la participation. Les trois types de flux concernés sont :

        - la rétention des non-exprimés du premier tour ;
        - la démobilisation commune des partis qualifiés ;
        - le report vers ``NON_EXPRIMES`` de chaque famille éliminée.

        La solution applique un même décalage aux logits, sauf lorsqu'une borne
        imposée par l'ordre partiel devient active. Il s'agit d'une
        projection entropique de chaque matrice tirée, calculable exactement en
        une dimension ; ce n'est pas l'I-projection de la loi jointe complète des
        501 circonscriptions, dont la densité induite n'est pas disponible.

        Le découpage suit ces trois temps : `_expressed_targets` tire les cibles,
        `_projection_channels` recense les flux d'une circonscription, et
        `_anchored_matrix` projette puis rebâtit sa matrice.
        """
        # Remis à zéro d'entrée : les trois sorties anticipées ci-dessous
        # délèguent au modèle non ancré sans rien tirer, et une trace laissée en
        # place serait relue comme celle de la simulation courante.
        self._drawn_national_change = None
        self._drawn_local_changes = None
        self._drawn_expressed_targets = None

        if not districts:
            return []

        first_round_shares, registered_voters = zip(
            *(self._first_round_expressed_share(district) for district in districts)
        )
        shares = np.asarray(first_round_shares)
        electorates = np.asarray(registered_voters)
        if electorates.sum() == 0:
            return super()._complete_matrices(rows_per_district, districts, draw)

        targets = self._expressed_targets(districts, shares, electorates)
        if targets is None:
            return super()._complete_matrices(rows_per_district, districts, draw)

        # Trois temps, et non une boucle unique : le recensement des réservoirs
        # ne consomme pas le générateur, donc les séparer de la projection ne
        # change aucun tirage — mais permet de résoudre les 501 contraintes
        # comptables ensemble plutôt qu'une par une.
        anchored: list[TransferMatrix | None] = [None] * len(districts)
        realised_shares: list[float] = [float("nan")] * len(districts)

        reservoirs_by_index: dict[int, _DistrictReservoirs] = {}
        for index, (rows, district, electorate) in enumerate(
            zip(rows_per_district, districts, registered_voters)
        ):
            if electorate <= 0:
                anchored[index] = super()._complete_matrices([rows], [district], draw)[
                    0
                ]
                continue
            reservoirs_by_index[index] = self._district_reservoirs(rows, district, draw)

        if reservoirs_by_index:
            projected = self._project_all(
                reservoirs_by_index, targets, registered_voters
            )
            for index, district_reservoirs in reservoirs_by_index.items():
                matrix, realised = self._anchored_matrix(
                    rows_per_district[index],
                    district_reservoirs,
                    draw,
                    projected[index],
                    registered_voters[index],
                )
                anchored[index] = matrix
                realised_shares[index] = realised

        self._drawn_expressed_targets = np.asarray(realised_shares)
        return [matrix for matrix in anchored if matrix is not None]

    @staticmethod
    def _project_all(
        reservoirs_by_index: Mapping[int, _DistrictReservoirs],
        targets: np.ndarray,
        registered_voters: Sequence[float],
    ) -> dict[int, np.ndarray]:
        """Résout la contrainte comptable de toutes les circonscriptions en bloc.

        Les circonscriptions n'ont pas le même nombre de réservoirs (4 à 8) : les
        colonnes en trop reçoivent ``votes = 0``, ce qui les laisse sans effet
        sur la contrainte comme sur les bornes.
        """
        indices = list(reservoirs_by_index)
        width = max(len(reservoirs_by_index[index].reservoirs) for index in indices)
        drawn = np.full((len(indices), width), 0.5)
        votes = np.zeros((len(indices), width))
        lowest = np.zeros((len(indices), width))
        highest = np.ones((len(indices), width))
        wanted = np.empty(len(indices))
        for row, index in enumerate(indices):
            reservoirs = reservoirs_by_index[index].reservoirs
            span = len(reservoirs)
            drawn[row, :span] = [r.drawn_rate for r in reservoirs]
            votes[row, :span] = [r.votes for r in reservoirs]
            lowest[row, :span] = [r.lowest_achievable_rate for r in reservoirs]
            highest[row, :span] = [r.highest_achievable_rate for r in reservoirs]
            wanted[row] = (1.0 - float(targets[index])) * registered_voters[index]

        projected = project_probabilities_batch(drawn, votes, wanted, lowest, highest)
        return {
            index: projected[row, : len(reservoirs_by_index[index].reservoirs)]
            for row, index in enumerate(indices)
        }


@dataclass
class NationalAnchoredModel(ExpressedShareAnchoredMixin, NationalModel):
    """National transfer model with district expressed-share anchoring."""


@dataclass
class KernelAnchoredModel(ExpressedShareAnchoredMixin, KernelModel):
    """Kernel transfer model with district expressed-share anchoring."""
