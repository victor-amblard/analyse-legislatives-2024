"""
Matrices de report, et leur restriction au bulletin d'une circonscription.

Ce fichier ne contient aucun aléa : les paramètres (rétention propre, tilt) sont
tirés dans `models` et arrivent ici en arguments. Mais il ne contient pas non plus
que des règles du scrutin — restreindre une matrice nationale à une
circonscription oblige à répondre à deux questions de modélisation, sans réponse
neutre possible : que deviennent les voix propres d'un qualifié, et comment se
répartissent les non-exprimés qui se mobilisent ? La ligne doit sommer à 1 sur les
destinations disponibles.

Hypothèses du billet (`writeup.fr.md`) implémentées ici :

- **Hypothèse 3** — un électeur d'un candidat qualifié peut se démobiliser mais
  pas voter pour un autre : voir la boucle sur `own_retention` dans
  `normalize_for_district` ;
- **Hypothèse 4** — la mobilisation des non-exprimés est proportionnelle à leur
  réservoir, répartie entre qualifiés selon leur score du 1er tour élevé à la
  puissance `non_expressed_tilt` : voir `_non_expressed_row`. Les variantes
  ancrées assouplissent cette hypothèse (`models.expressed_anchored`).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from analyse_legislatives.circonscription import CirconscriptionResult
from analyse_legislatives.parties import (
    NON_EXPRIMES,
    DESTINATIONS,
    Destination,
)

ZERO_DIVISION_FLOOR = 0.0


@dataclass(frozen=True)
class TransferMatrix:
    """
    Taux de report bruts, sous forme imbriquée `{source: {cible: taux}}`.

    Les taux ne somment PAS à 1 par ligne : ce sont des poids relatifs, que
    `normalize_for_district` restreint et renormalise selon les partis
    réellement qualifiés dans chaque circonscription.
    """

    rates: Mapping[Destination, Mapping[Destination, float]]

    own_retentions: Mapping[Destination, float] = field(default_factory=dict)
    """`{parti qualifié: probabilité qu'un de ses électeurs du 1er tour revienne
    voter}`. Vide par défaut, ce qui vaut 1 partout et redonne exactement le
    comportement historique.

    Rangée à part de `rates`, et non sur la diagonale : une ligne de `rates` est
    une distribution sur les DESTINATIONS, et les ordres de préférence ne
    contiennent jamais de destination vers soi-même (la ligne ENS+ liste toutes
    les familles sauf ENS+). Y glisser une diagonale casserait l'invariant « la
    ligne somme à 1 » sur lequel repose le tirage multinomial."""

    unavailable_targets: frozenset[Destination] = field(
        default_factory=frozenset, repr=False
    )
    """Destinations absentes du bulletin après normalisation.

    Cette information ne se déduit pas des taux nuls : un transfert possible
    peut valoir exactement zéro.
    """

    def __str__(self) -> str:
        """Table lisible des taux, en pourcentage et dans l'ordre canonique."""
        order = list(DESTINATIONS)
        labels = {destination: str(destination) for destination in order}
        source_width = max(len("source"), *(len(value) for value in labels.values()))
        column_widths = {
            destination: max(len(labels[destination]), len("100.0%"))
            for destination in order
        }

        header = (
            "source".ljust(source_width)
            + "  "
            + "  ".join(labels[target].rjust(column_widths[target]) for target in order)
        )
        lines = ["TransferMatrix", header, "─" * len(header)]

        for source in order:
            row = self.rates.get(source, {})
            cells = []
            for target in order:
                width = column_widths[target]
                if target in self.unavailable_targets:
                    value = "/"
                elif source == target and source != NON_EXPRIMES and target not in row:
                    value = "—"
                elif target not in row:
                    value = "·"
                else:
                    value = f"{float(row[target]):.1%}"
                cells.append(value.rjust(width))
            lines.append(labels[source].ljust(source_width) + "  " + "  ".join(cells))

        if self.own_retentions:
            retention = ", ".join(
                f"{labels[party]}={float(self.own_retentions[party]):.1%}"
                for party in order
                if party in self.own_retentions
            )
            lines.extend(("", f"own retention: {retention}"))

        return "\n".join(lines)

    def to_matrix(self, order: Sequence[Destination] | None = None) -> np.ndarray:
        """
        Matrice carrée dense, indexée dans `order` (par défaut l'ordre canonique
        `DESTINATIONS`). La diagonale est forcée à zéro — un parti éliminé ne se
        reporte pas sur lui-même — sauf pour NON_EXPRIMES, où `(NON_EXPRIMES, NON_EXPRIMES)` est la
        probabilité de rester non-exprimé du 1er tour.
        """
        order = list(DESTINATIONS if order is None else order)
        return np.array(
            [
                [
                    (
                        self.rates.get(source, {}).get(target, 0)
                        if source != target or source == NON_EXPRIMES
                        else 0
                    )
                    for target in order
                ]
                for source in order
            ]
        )

    @classmethod
    def from_matrix(
        cls,
        matrix: np.ndarray,
        order: Sequence[Destination] | None = None,
        *,
        unavailable_targets: frozenset[Destination] = frozenset(),
    ) -> "TransferMatrix":
        """Inverse de `to_matrix`."""
        order = list(DESTINATIONS if order is None else order)
        return cls(
            rates={
                source: {target: matrix[i, j] for j, target in enumerate(order)}
                for i, source in enumerate(order)
            },
            unavailable_targets=unavailable_targets,
        )

    def mix(self, other: "TransferMatrix", weight: float) -> "TransferMatrix":
        """Combinaison convexe cellule à cellule : `weight * self + (1 - weight) * other`."""
        if self.unavailable_targets != other.unavailable_targets:
            raise ValueError(
                "Impossible de mélanger des matrices dont les bulletins diffèrent."
            )
        return TransferMatrix(
            rates={
                source: {
                    target: weight * value + (1 - weight) * other.rates[source][target]
                    for target, value in targets.items()
                }
                for source, targets in self.rates.items()
            },
            unavailable_targets=self.unavailable_targets,
        )


@dataclass(frozen=True)
class _DistrictLayout:
    """
    Ces tableaux ne dépendent QUE des voix du 1er tour : ils sont identiques à chaque
    simulation.
    """

    order: tuple[Destination, ...]
    competing_mask: np.ndarray
    destination_mask: np.ndarray
    row_active: np.ndarray
    col_active: np.ndarray
    shares: np.ndarray
    n_competing: int


@lru_cache(maxsize=2048)
def _layout_for(competing: tuple[tuple[Destination, int], ...]) -> _DistrictLayout:
    """Mémorisé sur le CONTENU (les voix par parti) et non sur l'identifiant de
    circonscription : deux objets peuvent partager un identifiant sans partager
    leur configuration — c'est le cas dans les tests."""
    order = tuple(party for party, _ in competing)
    votes = np.array([v for _, v in competing])
    n = len(order)
    competing_mask = (votes > 0).astype(int)

    # Masque de destination (colonnes) : qui peut recevoir des voix. L'abstention
    # est toujours une destination valide (un électeur peut toujours choisir de
    # ne pas voter), qu'elle « concoure » ou non.
    destination_mask = competing_mask.copy()
    destination_mask[-1] = 1

    # Masque de source (lignes) : qui garde ses voix du 1er tour telles quelles
    # au lieu de les redistribuer (c'est le cas des partis qualifiés). NON_EXPRIMES ne
    # doit PAS être traitée comme « qualifiée » ici, sinon sa propre ligne est
    # annulée et les hyperparamètres de rétention deviennent du code mort.
    source_mask = competing_mask.copy()
    source_mask[-1] = 0

    total = votes.sum()
    shares = votes.astype(float) / total if total else np.zeros(n)

    layout = _DistrictLayout(
        order=order,
        competing_mask=competing_mask,
        destination_mask=destination_mask,
        row_active=np.tile(source_mask, (n, 1)).T,
        col_active=np.tile(destination_mask, (n, 1)),
        shares=shares,
        n_competing=int(destination_mask.sum()) - 1,
    )
    # Ces tableaux sont partagés par tous les appelants : les rendre non
    # inscriptibles transforme une mutation accidentelle en erreur immédiate.
    for array in (
        layout.competing_mask,
        layout.destination_mask,
        layout.row_active,
        layout.col_active,
        layout.shares,
    ):
        array.flags.writeable = False
    return layout


def normalize_for_district(
    matrix: TransferMatrix,
    district: CirconscriptionResult,
    non_expressed_tilt: float,
) -> TransferMatrix:
    """
    Restreint la matrice de report à la configuration réelle de la
    circonscription : seules les colonnes des partis effectivement qualifiés
    (plus NON_EXPRIMES, toujours disponible) sont conservées, et chaque ligne concernée
    est renormalisée pour sommer à 1.

    `non_expressed_tilt` gouverne la répartition des non-exprimés du 1er tour qui se mobilisent
    (voir `_non_expressed_row`). Le paramètre est OBLIGATOIRE : lui donner une valeur
    par défaut reviendrait à laisser un appelant hériter silencieusement d'une
    règle de répartition sans le savoir, et c'est précisément l'hypothèse la plus
    lourde de cette ligne.
    """
    layout = _layout_for(tuple(district.competing_parties_results.items()))
    order = list(layout.order)
    competing_mask = layout.competing_mask
    restricted = (1 - layout.row_active) * matrix.to_matrix(order) * layout.col_active

    row_max = restricted.max(axis=1, keepdims=True)
    scaled = np.divide(
        restricted,
        row_max,
        out=np.zeros_like(restricted, dtype=float),
        where=row_max > ZERO_DIVISION_FLOOR,
    )
    row_sums = scaled.sum(axis=1, keepdims=True)
    normalized = np.divide(
        scaled,
        row_sums,
        out=np.zeros_like(scaled, dtype=float),
        where=row_sums > ZERO_DIVISION_FLOOR,
    )

    # Une famille peut avoir DEUX candidats dans la même circonscription, dont un
    # seul qualifié (ex. deux candidats RN+) : les voix du candidat éliminé
    # rejoignent alors en totalité le qualifié de sa propre famille, comme les
    # voix du qualifié lui-même. Sans cette ligne, celle du parti qualifié est
    # entièrement nulle (annulée par `1 - row_active`) et le tirage multinomial
    # reverse tout le réservoir dans la dernière colonne, c'est-à-dire NON_EXPRIMES —
    # 886 000 voix nationalement, dont 41 % du réservoir éliminé du RN+.
    # La ligne porte aussi, le cas échéant, une RÉTENTION PROPRE : la probabilité
    # qu'un électeur du parti qualifié revienne voter. Absente, elle vaut 1 et on
    # retrouve l'identité. Le complément part aux non-exprimés et nulle part
    # ailleurs : un électeur d'un parti qualifié revient voter pour lui ou reste
    # chez lui. Le faire basculer vers l'adversaire serait une tout autre
    # affirmation, que les ordres de préférence ne décrivent pas — ils ne
    # s'appliquent qu'aux réservoirs ÉLIMINÉS.
    # HYPOTHÈSE 3 du billet : un électeur d'un candidat qualifié revient voter
    # pour lui (probabilité `own_retention`) ou ne s'exprime pas — jamais pour
    # l'adversaire. Le complément part donc entièrement vers NON_EXPRIMES.
    for i, is_competing in enumerate(competing_mask):
        if is_competing:
            own_retention = float(matrix.own_retentions.get(order[i], 1.0))
            normalized[i] = 0.0
            normalized[i, i] = own_retention
            normalized[i, -1] = 1.0 - own_retention

    normalized[-1] = _non_expressed_row(matrix, layout, non_expressed_tilt)
    unavailable_targets = frozenset(
        target
        for target, is_available in zip(order, layout.destination_mask)
        if not is_available
    )
    return TransferMatrix.from_matrix(
        normalized,
        order=order,
        unavailable_targets=unavailable_targets,
    )


def _non_expressed_row(
    matrix: TransferMatrix,
    layout: _DistrictLayout,
    non_expressed_tilt: float,
) -> np.ndarray:
    """Ligne des non-exprimés, restreinte aux qualifiés — HYPOTHÈSE 4 du billet.

    Une part `non_expressed_retention` du réservoir reste non exprimée ; le reste
    se répartit entre qualifiés au prorata de `score_1er_tour ** tilt`. La forme
    de cette répartition est la croyance ; son exposant est tiré dans `models`.

    Retention is a direct probability. The remaining mass is split with weights
    ``first_round_share ** non_expressed_tilt``; zero scores are masked before applying a
    negative exponent.
    """
    competing_mask = layout.competing_mask
    n = len(competing_mask)
    non_expressed_retention = matrix.rates.get(NON_EXPRIMES, {}).get(NON_EXPRIMES, 0)

    if layout.n_competing == 0:
        row = np.zeros(n)
        row[-1] = 1.0
        return row

    shares = layout.shares

    # Seuls les qualifiés sont élevés à la puissance : 0 ** non_expressed_tilt vaudrait
    # +inf pour un exposant négatif, et donnerait tout le réservoir à un parti
    # absent du 2nd tour.
    qualified = competing_mask.astype(bool)
    weights = np.zeros(n)
    weights[qualified] = shares[qualified] ** non_expressed_tilt
    weights /= weights.sum()

    row = (1 - non_expressed_retention) * weights
    row[-1] = non_expressed_retention
    return row
