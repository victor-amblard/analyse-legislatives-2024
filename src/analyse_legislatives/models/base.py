"""Mécanique commune de génération des matrices et des prédictions."""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import final

import numpy as np

from analyse_legislatives.circonscription import (
    CirconscriptionPrediction,
    CirconscriptionResult,
)
from analyse_legislatives.models.ordinal import draw_alpha, linear_extension
from analyse_legislatives.parties import (
    NON_EXPRIMES,
    DESTINATIONS,
    FAMILIES,
    Destination,
)
from analyse_legislatives.transfers import TransferMatrix, normalize_for_district
from analyse_legislatives.utils.validation import (
    check_beta_pair,
    check_bounds,
    check_positive_bounds,
)

TransferRow = Mapping[Destination, float]
"""Une ligne de report normalisée : destination -> taux."""

DistrictRows = Mapping[Destination, TransferRow]
"""Les lignes de report d'UNE circonscription, indexées par parti source.

En LECTURE (paramètres) : `Sequence[DistrictRows]`, covariant, accepte donc la
liste de `dict` que produit l'étape 2. En ÉCRITURE (retours) : `list[dict[...]]`,
le type concret, car `list` est invariant et `list[dict]` n'est pas un
`list[Mapping]`."""

DIRICHLET_CONCENTRATION: float = 1.0


@dataclass(frozen=True)
class SimulationParameters:
    """Paramètres globaux tirés une fois et partagés entre circonscriptions.

    Les variables latentes qui produisent les taux de report ne font pas partie de
    cet objet : elles sont tirées ensuite par chaque variante du modèle.
    """

    alpha: float
    extensions: Mapping[Destination, Sequence[Destination]]
    non_expressed_retention: float
    qualified_demobilisation: float
    mixing_weight: float
    tilt: float


@dataclass
class Model(ABC):
    transfer_orderings: Mapping[Destination, Sequence[Sequence[Destination]]]

    non_expressed_tilt_bounds: tuple[float, float]
    non_expressed_retention_prior: tuple[float, float]
    qualified_demobilisation_prior: tuple[float, float]
    mixing_prior: tuple[float, float]
    dirichlet_alpha_bounds: tuple[float, float]

    free_targets: tuple[Destination, ...] = ()

    rng: np.random.Generator = field(default_factory=np.random.default_rng)

    dirichlet_concentration: float | None = None
    qualified_demobilisation: float | None = None

    def __post_init__(self):
        if not self.transfer_orderings:
            raise ValueError("`transfer_orderings` manquant")
        missing = [
            source
            for source, tiers in self.transfer_orderings.items()
            if not any(tiers)
        ]
        if missing:
            raise ValueError(f"Ordres de préférence vides pour : {missing}.")

        # Mêmes contraintes qu'au chargement de `config/model.yaml`, écrites une
        # seule fois (`utils.validation`) : un modèle construit à la main — c'est
        # le cas de toutes les analyses de sensibilité — passe par ici et non par
        # le schéma pydantic.
        check_beta_pair(
            self.non_expressed_retention_prior, "non_expressed_retention_prior"
        )
        check_beta_pair(
            self.qualified_demobilisation_prior, "qualified_demobilisation_prior"
        )
        check_beta_pair(self.mixing_prior, "mixing_prior")
        check_bounds(self.non_expressed_tilt_bounds, "non_expressed_tilt_bounds")
        check_positive_bounds(self.dirichlet_alpha_bounds, "dirichlet_alpha_bounds")
        if (
            self.dirichlet_concentration is not None
            and self.dirichlet_concentration <= 0
        ):
            raise ValueError(
                "`dirichlet_concentration` doit être strictement positive."
            )
        if self.qualified_demobilisation is not None and not (
            0 <= self.qualified_demobilisation < 1
        ):
            raise ValueError("`qualified_demobilisation` doit appartenir à [0, 1).")

        overlap = [
            source
            for source, tiers in self.transfer_orderings.items()
            for tier in tiers
            if set(tier) & set(self.free_targets)
        ]
        if overlap:
            raise ValueError(
                f"Destinations à la fois ordonnées et libres pour : {set(overlap)}. "
                f"Une destination de `free_targets` ({self.free_targets}) ne doit pas "
                f"figurer dans `transfer_orderings`."
            )

        # Sans ce contrôle, une destination oubliée des deux côtés ne recevrait
        # jamais aucun report — silencieusement, et sans qu'aucune ligne cesse de
        # sommer à 1.
        for source in self.transfer_orderings:
            covered = set(self.row_targets(source))
            expected = set(DESTINATIONS) - {source}
            if covered != expected:
                raise ValueError(
                    f"La ligne {source} ne couvre pas toutes les destinations : "
                    f"manquantes {sorted(expected - covered)}, "
                    f"en trop {sorted(covered - expected)}."
                )

    def free_targets_for(self, source_party: Destination) -> list[Destination]:
        """Destinations libres de CETTE ligne : les libres, moins la source
        elle-même (un parti ne se reporte pas sur lui-même)."""
        return [t for t in self.free_targets if t != source_party]

    def row_targets(self, source_party: Destination) -> list[Destination]:
        """Toutes les destinations d'une ligne : celles soumises à l'ordre, puis les
        libres. C'est la structure de la ligne, indépendamment du tirage."""
        tiers = self.transfer_orderings[source_party]
        return [t for tier in tiers for t in tier] + self.free_targets_for(source_party)

    @property
    def matrix_cells(self) -> list[tuple[Destination, Destination]]:
        """Cellules effectivement tirées, dans l'ordre canonique des lignes."""
        return [
            (source, target)
            for source in self.transfer_orderings
            for target in self.row_targets(source)
        ] + [(NON_EXPRIMES, NON_EXPRIMES)]

    def draw_simulation(self) -> SimulationParameters:
        """Tire les paramètres globaux d'une simulation."""
        return SimulationParameters(
            alpha=draw_alpha(
                self.dirichlet_alpha_bounds, self.rng, self.dirichlet_concentration
            ),
            extensions={
                source: linear_extension(tiers, self.rng)
                for source, tiers in self.transfer_orderings.items()
            },
            non_expressed_retention=float(
                self.rng.beta(*self.non_expressed_retention_prior)
            ),
            qualified_demobilisation=float(
                self.qualified_demobilisation
                if self.qualified_demobilisation is not None
                else self.rng.beta(*self.qualified_demobilisation_prior)
            ),
            mixing_weight=float(self.rng.beta(*self.mixing_prior)),
            tilt=float(self.rng.uniform(*self.non_expressed_tilt_bounds)),
        )

    @abstractmethod
    def _sample_rows_per_district(
        self,
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> list[dict[Destination, TransferRow]]:
        """
        Étape 2 — les lignes de report des partis, une entrée par circonscription.

        La ligne des non-exprimés n'est PAS produite ici : c'est l'étape 3 qui la
        pose, et c'est là que les variantes ancrées divergent.
        """

    def _complete_matrices(
        self,
        rows_per_district: Sequence[DistrictRows],
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> list[TransferMatrix]:
        """
        Étape 3 — ferme chaque matrice avec la rétention des non-exprimés et la
        rétention propre des qualifiés.

        Ici les deux viennent directement du prior. Les variantes ancrées
        projettent au contraire l'ensemble des flux vers les non-exprimés pour
        atteindre une part de suffrages exprimés visée — d'où la redéfinition de
        cette seule méthode.
        """
        # Annoté `Destination` et non `PoliticalFamily` : `Mapping` est covariant
        # en VALEUR mais invariant en CLÉ, donc un `dict[PoliticalFamily, float]`
        # n'est pas un `Mapping[Destination, float]`.
        own_retentions: dict[Destination, float] = dict.fromkeys(
            FAMILIES, 1.0 - draw.qualified_demobilisation
        )
        return [
            TransferMatrix(
                {**rows, NON_EXPRIMES: {NON_EXPRIMES: draw.non_expressed_retention}},
                own_retentions=own_retentions,
            )
            for rows in rows_per_district
        ]

    @final
    def sample_transfer_matrices(
        self,
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters | None = None,
    ) -> list[TransferMatrix]:
        """
        Un tirage de la matrice de report par circonscription — c'est-à-dire un
        tirage dans la PRÉDICTIVE A PRIORI de la matrice, le modèle n'étant jamais
        conditionné à des données.

        Les paramètres peuvent être fournis pour contrôler les hypothèses globales du
        tirage, notamment dans les tests et les analyses de sensibilité.
        """
        if draw is None:
            draw = self.draw_simulation()
        rows = self._sample_rows_per_district(districts, draw)
        return self._complete_matrices(rows, districts, draw)

    # ------------------------------------------------------------ prédiction

    def _default_parameters(self) -> TransferMatrix:
        """Les variantes publiées tirent leurs matrices conjointement sur
        l'ensemble des circonscriptions ; une prédiction isolée exige donc une
        matrice explicite."""
        raise ValueError(
            "predict_circonscription() exige `parameters` ; sinon utiliser "
            "predict_all_circonscriptions() pour tirer les matrices conjointement."
        )

    def sample_transfers_in_circonscription(
        self,
        district: CirconscriptionResult,
        parameters: TransferMatrix,
        non_expressed_tilt: float,
    ) -> dict:
        """Tirage multinomial des voix de chaque réservoir (parti éliminé ou
        abstention) vers les destinations, selon la ligne normalisée."""
        normalized = normalize_for_district(parameters, district, non_expressed_tilt)

        transfers = {}
        for source, pool in district.available_vote_pools_by_party().items():
            row = normalized.rates[source]

            # np.random.Generator.multinomial ne lève rien si les probabilités ne
            # somment pas à 1 : il verse tout le reliquat dans la DERNIÈRE
            # colonne. Une ligne mal normalisée est donc silencieusement convertie
            # en « tout le réservoir part à l'abstention », ce qui a déjà masqué un
            # bug. On refuse explicitement ce cas.
            # `abs(... - 1) > 1e-5` et non `np.isclose` : même tolérance
            # effective (atol 1e-8 + rtol 1e-5 autour de 1), mais `isclose` est
            # un appel numpy complet pour comparer deux scalaires — il pesait à
            # lui seul 23 % du temps de simulation, sur 52 560 appels.
            row_total = sum(row.values())
            if pool > 0 and abs(row_total - 1.0) > 1e-5:
                raise ValueError(
                    f"Ligne de report non normalisée pour {source} dans "
                    f"{district.circonscription.id} : somme = {row_total:.6f}"
                )

            targets = list(row.keys())
            drawn = self.rng.multinomial(n=pool, pvals=list(row.values()))
            transfers[source] = dict(zip(targets, drawn))
        return transfers

    @final
    def predict_circonscription(
        self,
        district: CirconscriptionResult,
        parameters: TransferMatrix | None = None,
        non_expressed_tilt: float | None = None,
    ) -> CirconscriptionPrediction:
        if parameters is None:
            parameters = self._default_parameters()
        if non_expressed_tilt is None:
            non_expressed_tilt = float(
                self.rng.uniform(*self.non_expressed_tilt_bounds)
            )

        transfers = self.sample_transfers_in_circonscription(
            district, parameters, non_expressed_tilt
        )
        # Rien n'est ajouté hors matrice : les voix des qualifiés y transitent
        # comme les autres (voir `available_vote_pools_by_party`), donc chaque
        # bulletin du 1er tour est compté une fois et une seule.
        return CirconscriptionPrediction(
            district.circonscription,
            {
                target: sum(row.get(target, 0) for row in transfers.values())
                for target in DESTINATIONS
            },
        )

    def local_shock_field(
        self, districts: Sequence[CirconscriptionResult]
    ) -> np.ndarray:
        """Champ de chocs locaux centrés réduits, un par circonscription.

        Indépendant par défaut : sans structure de dépendance déclarée, deux
        circonscriptions n'ont aucune raison de dévier ensemble. `KernelModel` le
        corrèle par son noyau. Utilisé par l'ancrage des suffrages exprimés pour
        `delta_c`.
        """
        return self.rng.standard_normal(len(districts))

    def tilts_for_districts(
        self,
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> np.ndarray:
        """Tilt de remobilisation, une valeur par circonscription.

        National par défaut : la valeur tirée dans `draw` est diffusée partout,
        comme les cellules des lignes de report dans les variantes nationales.
        `KernelModel` la localise, pour la même raison qu'il localise les reports
        (hypothèse 6) — sans quoi le plus gros réservoir de voix serait le seul
        dont la destination ne varierait pas d'une circonscription à l'autre.
        """
        return np.full(len(districts), draw.tilt, dtype=float)

    @final
    def predict_all_circonscriptions(
        self, districts: Sequence[CirconscriptionResult]
    ) -> list[CirconscriptionPrediction]:
        """Une simulation complète : un tirage national, puis une prédiction par
        circonscription qui en découle."""
        draw = self.draw_simulation()
        matrices = self.sample_transfer_matrices(districts, draw)
        tilts = self.tilts_for_districts(districts, draw)
        return [
            self.predict_circonscription(district, matrix, float(tilt))
            for district, matrix, tilt in zip(districts, matrices, tilts)
        ]
