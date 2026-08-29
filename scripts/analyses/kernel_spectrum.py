"""
Analyse spectrale du noyau de corrélation spatiale de `KernelModel`.

Le noyau K (une circonscription par ligne/colonne) est ce qui fait que des
circonscriptions politiquement proches au 1er tour partagent des reports
corrélés au 2nd. Sa décomposition en valeurs propres répond à deux questions
qu'aucune simulation ne renseigne directement :

1. **Combien de structure "spatiale" le noyau capture-t-il réellement ?** Le
   rang effectif (participation ratio) vaut `n` pour un noyau identité (toutes
   les circonscriptions indépendantes) et 1 pour un noyau de rang 1 (toutes
   parfaitement corrélées par un seul facteur national). Une valeur proche de 1
   signifierait que "corrélation spatiale" est essentiellement un swing
   national plus du bruit, pas une structure géographique fine.

2. **Que représentent les modes qui dominent ?** En corrélant chaque vecteur
   propre dominant avec les dimensions de l'embedding 1er tour (parts de voix
   par famille + abstention), on peut lire si un mode EST essentiellement
   "le score RN+" ou une combinaison diffuse sans lecture politique simple.

En complément, ce script fait varier la bande passante `h` autour de sa valeur
par défaut (heuristique de la médiane) : `h` n'est pas calibré, c'est un choix
standard en méthodes à noyau, donc voir à quel point le spectre y est sensible
renseigne sur la robustesse de "kernel" à ce choix.

Usage :
    python scripts/analyses/kernel_spectrum.py
    python scripts/analyses/kernel_spectrum.py --bandwidth-multipliers 0.1 0.5 1 2 10
    python scripts/analyses/kernel_spectrum.py --top 8
"""

from collections.abc import Sequence
import argparse

import numpy as np
import pandas as pd

from analyse_legislatives.data import load_full_results
from analyse_legislatives.config import DEFAULT_SEED
from analyse_legislatives.models import build
from analyse_legislatives.circonscription import CirconscriptionResult
from analyse_legislatives.models.kernel import KernelModel
from analyse_legislatives.parties import NON_EXPRIMES, FAMILIES

DEFAULT_MULTIPLIERS = [0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0]
"""Multiplicateurs de la bande passante par défaut balayés par la sensibilité.
Centrés sur 1 (= la valeur effectivement utilisée par le modèle), étendus sur
deux ordres de grandeur dans chaque direction pour voir les deux régimes
limites : noyau ~identité (h petit) et noyau ~rang 1 (h grand)."""


def spectrum(kernel: np.ndarray) -> np.ndarray:
    """Valeurs propres décroissantes d'un noyau symétrique, tronquées à 0 : les
    éventuelles valeurs négatives ne sont que du bruit d'arrondi sur une matrice
    positive semi-définie par construction (un noyau gaussien l'est toujours)."""
    eigvals = np.linalg.eigvalsh(kernel)[::-1]
    return np.clip(eigvals, 0, None)


def participation_ratio(eigvals: np.ndarray) -> float:
    """
    Rang effectif : (somme lambda)^2 / somme(lambda^2).

    Vaut `n` pour un noyau identité (n valeurs propres égales : autant de
    facteurs indépendants que de circonscriptions) et 1 pour un noyau de rang 1
    (une seule valeur propre non nulle : un seul facteur commun explique tout).
    C'est la version continue et sans seuil arbitraire de "combien de
    composantes comptent".
    """
    return float(eigvals.sum() ** 2 / (eigvals**2).sum())


def n_components_for(eigvals: np.ndarray, threshold: float = 0.9) -> int:
    """Nombre minimal de composantes dont la somme cumulée atteint `threshold` de
    la variance totale du noyau (mesure complémentaire au rang effectif, plus
    lisible mais dépendante d'un seuil)."""
    cumulative = np.cumsum(eigvals) / eigvals.sum()
    return int(np.searchsorted(cumulative, threshold) + 1)


def bandwidth_sweep(
    model: KernelModel,
    districts: Sequence[CirconscriptionResult],
    multipliers: Sequence[float],
) -> pd.DataFrame:
    """Rang effectif et concentration du spectre pour chaque multiplicateur de la
    bande passante par défaut du modèle."""
    default_h = model.kernel_bandwidth_for(districts)
    rows = []
    for m in multipliers:
        h = default_h * m
        eigvals = spectrum(model.kernel_matrix_for(districts, bandwidth=h))
        rows.append(
            {
                "multiplicateur": m,
                "bandwidth": h,
                "rang_effectif": participation_ratio(eigvals),
                "composantes_pour_90pct": n_components_for(eigvals, 0.9),
                "part_valeur_propre_1": eigvals[0] / eigvals.sum(),
            }
        )
    return pd.DataFrame(rows).set_index("multiplicateur")


def leading_modes(
    model: KernelModel, districts: Sequence[CirconscriptionResult], top: int
) -> pd.DataFrame:
    """Corrélation (Pearson, entre circonscriptions) des `top` premiers vecteurs
    propres du noyau, à sa bande passante par défaut, avec chaque dimension de
    l'embedding 1er tour — pour donner une lecture politique aux modes
    dominants plutôt que de s'arrêter à leur seule part de variance."""
    kernel = model.kernel_matrix_for(districts)
    eigvals, eigvecs = np.linalg.eigh(kernel)
    order = np.argsort(eigvals)[::-1]
    eigvals, eigvecs = eigvals[order], eigvecs[:, order]

    embeddings = np.array([model._district_embedding(d) for d in districts])
    dims = [str(p) for p in FAMILIES] + [str(NON_EXPRIMES)]

    rows = {}
    for i in range(min(top, len(eigvals))):
        mode = eigvecs[:, i]
        label = f"mode {i + 1} ({eigvals[i] / eigvals.sum():.1%} de la variance)"
        rows[label] = {
            dim: float(np.corrcoef(mode, embeddings[:, j])[0, 1])
            for j, dim in enumerate(dims)
        }
    return pd.DataFrame(rows).T


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--bandwidth-multipliers",
        type=float,
        nargs="+",
        default=DEFAULT_MULTIPLIERS,
    )
    parser.add_argument(
        "--top", type=int, default=5, help="nombre de modes propres à interpréter"
    )
    args = parser.parse_args()

    districts = load_full_results().districts
    model = build("kernel_anchored", seed=args.seed)
    print(f"{len(districts)} circonscriptions.")

    default_h = model.kernel_bandwidth_for(districts)
    default_eigvals = spectrum(model.kernel_matrix_for(districts))

    print("\n" + "=" * 72)
    print(f"SPECTRE DU NOYAU — bande passante par défaut (médiane) = {default_h:.4f}")
    print("=" * 72)
    print(
        f"Rang effectif (participation ratio) : "
        f"{participation_ratio(default_eigvals):.2f} / {len(districts)}"
    )
    print(
        f"Composantes nécessaires pour 90% de la variance : "
        f"{n_components_for(default_eigvals, 0.9)}"
    )
    print(
        f"Part de la 1ère valeur propre : {default_eigvals[0] / default_eigvals.sum():.1%}"
    )

    print("\n--- Interprétation des modes dominants ---")
    print(leading_modes(model, districts, args.top).round(3).to_string())
    print(
        "\nLecture : une corrélation forte (proche de ±1) avec une seule dimension "
        "signale un mode interprétable (« cet axe du noyau EST essentiellement le "
        "score RN+ ») ; une corrélation diffuse sur plusieurs dimensions signale un "
        "mode sans lecture politique simple."
    )

    print("\n" + "=" * 72)
    print("SENSIBILITÉ À LA BANDE PASSANTE")
    print("=" * 72)
    table = bandwidth_sweep(model, districts, args.bandwidth_multipliers)
    print(table.round(4).to_string())
    print(
        f"\nLecture : multiplicateur = 1 est la bande passante effectivement "
        f"utilisée par le modèle ({default_h:.4f}, heuristique de la médiane). Un "
        f"rang effectif proche de 1 = circonscriptions quasi parfaitement "
        f"corrélées (un seul facteur national) ; proche de {len(districts)} = "
        "quasi indépendantes. 'part_valeur_propre_1' est la part de variance "
        "captée par le seul mode dominant — sa sensibilité à `h` mesure si le "
        "diagnostic « le noyau est presque un swing national » (voir la section "
        "précédente) est un artefact du choix de bande passante ou tient sur "
        "plusieurs ordres de grandeur de `h`."
    )


if __name__ == "__main__":
    main()
