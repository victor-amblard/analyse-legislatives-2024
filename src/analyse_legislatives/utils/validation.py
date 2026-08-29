"""
Contraintes numériques partagées par le schéma de configuration et les modèles.

Les mêmes couples de flottants sont validés à deux moments qui ne se recouvrent
pas :

- au **chargement de `config/model.yaml`**, où le schéma pydantic donne le chemin
  du champ fautif et le nom du fichier ;
- à la **construction d'un `Model`**, qui peut recevoir des valeurs venues
  d'ailleurs — les analyses de sensibilité en passent qui ne figurent dans aucun
  YAML.

Écrire la contrainte ici plutôt que deux fois évite qu'elles divergent, sans
faire dépendre `models` (la mécanique statistique, réutilisable pour un autre
scrutin) du schéma propre aux législatives 2024.

Chaque fonction renvoie la valeur validée, ce qui la rend utilisable telle quelle
comme ``AfterValidator`` pydantic. `name` n'est renseigné que du côté des
modèles : pydantic préfixe déjà ses erreurs du chemin du champ.
"""

from collections.abc import Sequence

FloatPair = tuple[float, float]


def _unpack(value: Sequence[float], name: str, expected: str) -> FloatPair:
    prefix = f"`{name}` " if name else ""
    try:
        first, second = value
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{prefix}attend exactement deux valeurs ({expected}), reçu {value!r}."
        ) from exc
    return float(first), float(second)


def check_beta_pair(value: Sequence[float], name: str = "") -> FloatPair:
    """Les deux paramètres d'une loi Beta, tous deux strictement positifs.

    `numpy.random.Generator.beta` refuse bien un paramètre négatif, mais au
    moment du TIRAGE : pour un prior qu'une seule variante consomme, l'erreur
    remontait au milieu d'une simulation de plusieurs minutes, sans nommer le
    champ en cause.
    """
    prefix = f"`{name}` " if name else ""
    a, b = _unpack(value, name, "deux paramètres Beta")
    if a <= 0 or b <= 0:
        raise ValueError(
            f"{prefix}attend deux paramètres Beta strictement positifs, "
            f"reçu {value!r}."
        )
    return a, b


def check_bounds(value: Sequence[float], name: str = "") -> FloatPair:
    """Deux bornes croissantes, de signe quelconque.

    Une borne inférieure supérieure à la borne haute ne fait pas échouer
    `Generator.uniform` : elle tire simplement dans un intervalle retourné, ce
    qui inverse silencieusement la croyance déclarée.
    """
    prefix = f"`{name}` " if name else ""
    low, high = _unpack(value, name, "deux bornes")
    if high <= low:
        raise ValueError(f"{prefix}attend deux bornes croissantes, reçu {value!r}.")
    return low, high


def check_positive_bounds(value: Sequence[float], name: str = "") -> FloatPair:
    """Deux bornes croissantes ET strictement positives.

    Requis partout où les bornes sont passées au logarithme — un alpha tiré
    log-uniformément, par exemple.
    """
    prefix = f"`{name}` " if name else ""
    low, high = _unpack(value, name, "deux bornes")
    if low <= 0 or high <= low:
        raise ValueError(
            f"{prefix}attend deux bornes strictement positives et croissantes, "
            f"reçu {value!r}."
        )
    return low, high
