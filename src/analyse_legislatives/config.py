"""
Chargement de la configuration scientifique des législatives 2024.

Séparé des `models` (qui ne contiennent que la mécanique statistique,
réutilisable pour d'autres élections) et de `viz` (présentation) : ce module
rassemble les valeurs propres à ce scrutin, partagées par l'application Streamlit
et les scripts, pour qu'elles ne divergent pas entre les deux.

La source de vérité est `config/model.yaml`. Ce module le valide via un schéma
pydantic, convertit ses labels en objets du domaine, puis expose des constantes
Python aux modèles, à l'application et aux scripts. Modifier un prior ou un ordre
dans le YAML affecte donc tous les usages sans recopier la valeur dans le code.

Le schéma est ici, et non dans `models`, parce qu'il valide un FICHIER : formes,
longueurs, signes et vocabulaire des destinations, au chargement, avec le chemin
du champ fautif dans le message. Les invariants qui portent sur un modèle
quelconque — couverture complète des destinations par chaque ligne, disjonction
entre destinations libres et ordonnées — restent dans `Model.__post_init__`, où
ils protègent aussi qui instancie un modèle sans passer par ce YAML.
"""

import os
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    PositiveFloat,
    PositiveInt,
    ValidationError,
)

from analyse_legislatives.parties import Destination
from analyse_legislatives.utils.validation import (
    check_beta_pair,
    check_bounds,
    check_positive_bounds,
)

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent
DATA_DIR = Path(os.environ.get("ANALYSE_LEGISLATIVES_DATA_DIR", PROJECT_ROOT / "data"))
APP_ARTIFACT_DIR = PROJECT_ROOT / "artifacts/app"
MODEL_CONFIG_PATH = PROJECT_ROOT / "config/model.yaml"
PARTY_FAMILIES_PATH = PROJECT_ROOT / "config/party_families.json"


BetaPair = Annotated[tuple[float, float], AfterValidator(check_beta_pair)]
"""Les deux paramètres d'une loi Beta, tous deux strictement positifs.

`tuple[float, float]` impose la longueur — c'est ce qui manquait à `tuple(...)`,
où une liste de trois valeurs passait le chargement pour ne casser qu'au tirage —
et `check_beta_pair` porte la contrainte de signe, la même que celle appliquée à
la construction d'un `Model` (voir `utils.validation`)."""

Bounds = Annotated[tuple[float, float], AfterValidator(check_bounds)]
PositiveBounds = Annotated[tuple[float, float], AfterValidator(check_positive_bounds)]


class Priors(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    non_expressed_retention_beta: BetaPair
    non_expressed_tilt_uniform: Bounds
    qualified_demobilisation_beta: BetaPair
    mixing_beta: BetaPair
    dirichlet_alpha_bounds: PositiveBounds


class ExpressedShare(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_change_pts: float
    """Peut être négatif : la participation baisse habituellement au 2nd tour."""

    national_band_pts: PositiveFloat
    district_band_pts: PositiveFloat


class ModelConfig(BaseModel):
    """Schéma de `config/model.yaml`.

    `extra="forbid"` est délibéré : une clé mal orthographiée (`n_simulation`)
    serait sinon ignorée en silence et le défaut du code s'appliquerait, ce qui
    est le pire des cas pour un fichier censé être la source de vérité."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seed: int
    n_simulations: PositiveInt
    default_model: str
    priors: Priors
    expressed_share: ExpressedShare
    free_targets: tuple[Destination, ...]
    transfer_orderings: dict[Destination, list[list[Destination]]]


def load_model_config(path: Path = MODEL_CONFIG_PATH) -> ModelConfig:
    """Charge et valide la configuration, en nommant le fichier en cas d'échec.

    Pydantic donne le chemin du champ fautif mais ignore d'où vient la donnée :
    sans ce ré-emballage, une erreur levée à l'import ne dirait pas quel fichier
    corriger."""
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"{path} doit contenir un mapping YAML à la racine.")
    try:
        return ModelConfig.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Configuration invalide dans {path} :\n{exc}") from exc


MODEL_CONFIG = load_model_config()
PRIORS = MODEL_CONFIG.priors

DEFAULT_SEED = MODEL_CONFIG.seed
"""Seed du générateur aléatoire : deux exécutions avec cette valeur donnent des
projections strictement identiques. La changer permet d'évaluer la sensibilité des
résultats au tirage Monte-Carlo (voir scripts/analyses/diagnostics.py)."""

DEFAULT_N_SIMUS = MODEL_CONFIG.n_simulations
DEFAULT_MODEL = MODEL_CONFIG.default_model
DEFAULT_NON_EXPRESSED_RETENTION_PRIOR = PRIORS.non_expressed_retention_beta
DEFAULT_NON_EXPRESSED_TILT_BOUNDS = PRIORS.non_expressed_tilt_uniform
DEFAULT_QUALIFIED_DEMOBILISATION_PRIOR = PRIORS.qualified_demobilisation_beta
"""Prior Beta du taux national minimal de démobilisation des qualifiés."""
DEFAULT_MIXING_PRIOR = PRIORS.mixing_beta
DEFAULT_DIRICHLET_ALPHA_BOUNDS = PRIORS.dirichlet_alpha_bounds
"""Bornes de la loi log-uniforme d'alpha, tiré une fois par simulation au
niveau national."""
EXPRESSED_SHARE = MODEL_CONFIG.expressed_share
DEFAULT_EXPECTED_EXPRESSED_CHANGE_PTS = EXPRESSED_SHARE.expected_change_pts
"""Expected change in valid votes as a share of registered voters."""

DEFAULT_NATIONAL_EXPRESSED_BAND_PTS = EXPRESSED_SHARE.national_band_pts
"""Half-width of the national 90% band, in percentage points."""

DEFAULT_DISTRICT_EXPRESSED_BAND_PTS = EXPRESSED_SHARE.district_band_pts
"""Half-width of the district-level 90% band."""

DEFAULT_FREE_TARGETS = MODEL_CONFIG.free_targets
DEFAULT_TRANSFER_ORDERINGS: dict[Destination, list[list[Destination]]] = (
    MODEL_CONFIG.transfer_orderings
)
