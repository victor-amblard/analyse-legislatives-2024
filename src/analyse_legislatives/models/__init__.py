"""Variantes publiques du modèle et fabrique commune.

`national` partage une matrice entre toutes les circonscriptions ; `kernel` y
ajoute des variations locales corrélées entre circonscriptions d'un même
département ; `national_anchored` et `kernel_anchored` sont leurs pendants avec
ancrage des suffrages exprimés. Les quatre forment un plan croisé, ce qui permet
de lire séparément l'effet de la dépendance et celui de l'ancrage. La
construction des lignes ordinales est isolée dans
:mod:`analyse_legislatives.models.ordinal`.

Les six hypothèses numérotées de `writeup.fr.md` sont signalées en commentaire à
l'endroit où elles sont implémentées ; le README en donne la table complète. Deux
d'entre elles (3 et 4) vivent dans `transfers`, qui explique pourquoi.
"""

from collections.abc import Mapping, Sequence
import numpy as np

from analyse_legislatives.config import (
    DEFAULT_NON_EXPRESSED_RETENTION_PRIOR,
    DEFAULT_NON_EXPRESSED_TILT_BOUNDS,
    DEFAULT_QUALIFIED_DEMOBILISATION_PRIOR,
    DEFAULT_DISTRICT_EXPRESSED_BAND_PTS,
    DEFAULT_DIRICHLET_ALPHA_BOUNDS,
    DEFAULT_EXPECTED_EXPRESSED_CHANGE_PTS,
    DEFAULT_NATIONAL_EXPRESSED_BAND_PTS,
    DEFAULT_FREE_TARGETS,
    DEFAULT_DEPARTMENT_CORRELATION_PRIOR,
    DEFAULT_REGION_CORRELATION_PRIOR,
    DEFAULT_MIXING_PRIOR,
    DEFAULT_MODEL,
    DEFAULT_SEED,
    DEFAULT_TRANSFER_ORDERINGS,
)
from analyse_legislatives.models.base import (
    DIRICHLET_CONCENTRATION,
    Model,
    SimulationParameters,
)
from analyse_legislatives.models.copula import CopulaModel
from analyse_legislatives.models.kernel import KernelModel
from analyse_legislatives.models.national import NationalModel
from analyse_legislatives.models.expressed_anchored import (
    KernelAnchoredModel,
    NationalAnchoredModel,
)
from analyse_legislatives.parties import Destination
from analyse_legislatives.transfers import TransferMatrix

MODELS: dict[str, type[Model]] = {
    "national": NationalModel,
    "national_anchored": NationalAnchoredModel,
    "kernel": KernelModel,
    "kernel_anchored": KernelAnchoredModel,
}

STOCHASTIC_MODELS: tuple[str, ...] = tuple(MODELS)

PUBLICATION_MODELS: tuple[str, ...] = (
    "national",
    "national_anchored",
    "kernel",
    "kernel_anchored",
)
"""Les quatre cases du plan croisé « ancrage x dépendance ».

`kernel` — la dépendance sans l'ancrage — n'existait pas comme variante
publiée : la comparaison ne pouvait donc lire que l'effet du noyau SACHANT
l'ancrage, et n'aurait pas su dire lequel des deux porte le gain. La case
complète le plan."""

NON_EXPRESSED_TILT_BOUNDS = DEFAULT_NON_EXPRESSED_TILT_BOUNDS
NON_EXPRESSED_TILT_MIDPOINT = sum(NON_EXPRESSED_TILT_BOUNDS) / 2
MIXING_PRIOR = DEFAULT_MIXING_PRIOR


def build(
    name: str = DEFAULT_MODEL,
    *,
    seed: int = DEFAULT_SEED,
    non_expressed_retention_prior: tuple[
        float, float
    ] = DEFAULT_NON_EXPRESSED_RETENTION_PRIOR,
    non_expressed_tilt_bounds: tuple[float, float] = DEFAULT_NON_EXPRESSED_TILT_BOUNDS,
    transfer_orderings: (
        Mapping[Destination, Sequence[Sequence[Destination]]] | None
    ) = None,
    free_targets: tuple[Destination, ...] = DEFAULT_FREE_TARGETS,
    qualified_demobilisation_prior: tuple[
        float, float
    ] = DEFAULT_QUALIFIED_DEMOBILISATION_PRIOR,
    qualified_demobilisation: float | None = None,
    dirichlet_concentration: float | None = None,
    dirichlet_alpha_bounds: tuple[float, float] = DEFAULT_DIRICHLET_ALPHA_BOUNDS,
    **kwargs,
) -> Model:
    """
    Construit une variante du modèle avec la configuration par défaut du scrutin.

    Point d'entrée unique : tout appelant qui a besoin d'un modèle passe par ici,
    de sorte qu'ajouter un paramètre le propage partout au lieu de créer une
    divergence silencieuse entre l'app, l'évaluation et les diagnostics.
    """
    if name not in MODELS:
        raise ValueError(
            f"Modèle inconnu : {name!r}. Choix possibles : {', '.join(MODELS)}."
        )
    # `expressed_anchored` réclame trois croyances explicites. Elles sont DÉCLARÉES
    # dans `config/model.yaml` — donc lisibles et contestables — et non posées en
    # défaut dans le code. Le garde-fou du modèle reste actif pour quiconque
    # l'instancie directement.
    if name in ("kernel", "kernel_anchored"):
        kwargs = {
            "department_correlation_prior": DEFAULT_DEPARTMENT_CORRELATION_PRIOR,
            "region_correlation_prior": DEFAULT_REGION_CORRELATION_PRIOR,
        } | kwargs
    if name in ("national_anchored", "kernel_anchored"):
        kwargs = {
            "expected_expressed_change_pts": DEFAULT_EXPECTED_EXPRESSED_CHANGE_PTS,
            "national_expressed_band_pts": DEFAULT_NATIONAL_EXPRESSED_BAND_PTS,
            "district_expressed_band_pts": DEFAULT_DISTRICT_EXPRESSED_BAND_PTS,
        } | kwargs

    return MODELS[name](
        transfer_orderings=transfer_orderings or DEFAULT_TRANSFER_ORDERINGS,
        non_expressed_retention_prior=non_expressed_retention_prior,
        non_expressed_tilt_bounds=non_expressed_tilt_bounds,
        qualified_demobilisation_prior=qualified_demobilisation_prior,
        qualified_demobilisation=qualified_demobilisation,
        mixing_prior=DEFAULT_MIXING_PRIOR,
        free_targets=free_targets,
        dirichlet_concentration=dirichlet_concentration,
        dirichlet_alpha_bounds=dirichlet_alpha_bounds,
        rng=np.random.default_rng(seed),
        **kwargs,
    )


__all__ = [
    "MODELS",
    "STOCHASTIC_MODELS",
    "PUBLICATION_MODELS",
    "DEFAULT_MODEL",
    "NON_EXPRESSED_TILT_BOUNDS",
    "NON_EXPRESSED_TILT_MIDPOINT",
    "DIRICHLET_CONCENTRATION",
    "MIXING_PRIOR",
    "Model",
    "SimulationParameters",
    "CopulaModel",
    "KernelModel",
    "NationalAnchoredModel",
    "KernelAnchoredModel",
    "NationalModel",
    "TransferMatrix",
    "build",
]
