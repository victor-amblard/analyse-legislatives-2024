"""
Choisir la similarité du noyau SANS regarder le second tour.

Le variogramme des résidus (`residual_variogram.py`) répond à la question « quelle
similarité gouverne les écarts locaux ? », mais il lit les résultats du second
tour : s'en servir pour choisir le noyau revient à spécifier le modèle en
connaissant le résultat. Ce script pose la même question avec les seules données
disponibles AVANT le second tour.

L'observable est la part de suffrages exprimés du PREMIER tour — le `X` du modèle,
et la variable même que l'ancrage prend comme point de départ. On mesure sa
structure spatiale de deux façons concurrentes :

  - par la distance de Hellinger entre compositions politiques ;
  - par l'appartenance au même département.

Le test décisif est le troisième bloc : parmi les paires POLITIQUEMENT ÉLOIGNÉES
(dernier tiers des distances de Hellinger), les circonscriptions d'un même
département se ressemblent-elles encore ? Si oui, la géographie porte une
information que la similarité politique ne capture pas — et c'est une conclusion
tirée du seul premier tour.

LIMITE À NE PAS ESCAMOTER : ce diagnostic mesure la structure des NIVEAUX de
participation, alors que `delta_c` modélise l'écart local du CHANGEMENT entre les
deux tours. Que les niveaux soient groupés géographiquement rend plausible que les
variations le soient aussi, mais ne le démontre pas. C'est un argument a priori,
pas une validation.

Usage :
    python scripts/analyses/first_round_variogram.py
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl
from scipy.special import logit
from scipy.spatial.distance import pdist, squareform

from analyse_legislatives.config import PROJECT_ROOT
from analyse_legislatives.data import load_full_results
from analyse_legislatives.models.kernel import department_group
from analyse_legislatives.parties import FAMILIES

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "publication" / "sensitivity"
N_BINS = 8


def standardise(values: np.ndarray) -> np.ndarray:
    """Centre et réduit : les produits croisés s'interprètent en corrélation."""
    centred = values - values.mean()
    return centred / centred.std()


def pair_correlation(residual: np.ndarray, mask: np.ndarray) -> float:
    """Corrélation des paires sélectionnées, normalisée donc bornée dans [-1, 1].

    La moyenne brute des produits `e_c e_c'` n'estime une corrélation que sur une
    population homogène : sur un sous-ensemble dont les résidus sont plus dispersés
    que la moyenne — les gros départements urbains, par exemple — elle dépasse 1,
    ce qui n'a pas de sens. On normalise donc par la dispersion des seules
    circonscriptions impliquées dans les paires retenues.
    """
    iu = np.triu_indices(len(residual), k=1)
    left, right = iu[0][mask], iu[1][mask]
    if left.size == 0:
        return float("nan")
    a, b = residual[left], residual[right]
    return float((a * b).sum() / np.sqrt((a**2).sum() * (b**2).sum()))


def hellinger_distances(districts) -> np.ndarray:
    """Distances politiques du premier tour, indépendantes du noyau du modèle."""
    rows = []
    for district in districts:
        votes = np.array(
            [
                district.competing_parties_results.get(p, 0)
                + district.eliminated_parties_results.get(p, 0)
                for p in FAMILIES
            ]
            + [district.non_expressed],
            dtype=float,
        )
        rows.append(votes / votes.sum())
    return squareform(pdist(np.sqrt(rows), metric="euclidean")) / np.sqrt(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metropole-only",
        action="store_true",
        help=(
            "écarte l'outre-mer et l'étranger, dont la participation est atypique "
            "et dont le 'département' est une catégorie très particulière"
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    # AUCUN appel à `load_second_round_results` dans ce script : c'est le point.
    first_round = load_full_results()
    districts = first_round.districts
    if args.metropole_only:
        districts = [d for d in districts if not d.circonscription.is_overseas()]
    ids = [d.circonscription.id for d in districts]

    expressed, registered = [], []
    for district in districts:
        n_registered = first_round.inscrits_by_id[district.circonscription.id]
        votes = sum(
            district.competing_parties_results.get(p, 0)
            + district.eliminated_parties_results.get(p, 0)
            for p in FAMILIES
        )
        expressed.append(votes / n_registered)
        registered.append(n_registered)
    shares = np.clip(np.asarray(expressed), 1e-6, 1 - 1e-6)

    hellinger = hellinger_distances(districts)

    departements = np.array([department_group(i) for i in ids])
    iu = np.triu_indices(len(ids), k=1)
    distance = hellinger[iu]
    same_dept = (departements[:, None] == departements[None, :])[iu]

    residual = standardise(logit(shares))

    print("=" * 74)
    print("STRUCTURE SPATIALE DE LA PART DE SUFFRAGES EXPRIMÉS AU 1er TOUR")
    print(f"{len(ids)} circonscriptions, {len(set(departements))} départements")
    print("Aucun résultat du second tour n'intervient.")
    print("=" * 74)

    rows = []
    print("\n1. Par distance politique (Hellinger)")
    print(f"  {'distance H':>16s} {'paires':>9s} {'corrélation':>13s}")
    edges = np.quantile(distance, np.linspace(0, 1, N_BINS + 1))
    edges[-1] += 1e-9
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (distance >= lo) & (distance < hi)
        rho = pair_correlation(residual, m)
        print(f"  {lo:.3f}–{hi:.3f} {int(m.sum()):9d} {rho:13.3f}")
        rows.append(
            {
                "test": "hellinger",
                "borne_min": float(lo),
                "borne_max": float(hi),
                "paires": int(m.sum()),
                "correlation": rho,
            }
        )

    print("\n2. Par département")
    for label, m in (
        ("même département", same_dept),
        ("départements différents", ~same_dept),
    ):
        rho = pair_correlation(residual, m)
        print(f"  {label:<26s} {int(m.sum()):8d} paires | corrélation {rho:+.3f}")
        rows.append(
            {
                "test": "departement",
                "groupe": label,
                "paires": int(m.sum()),
                "correlation": rho,
            }
        )

    # Le test décisif : la géographie survit-elle quand la politique ne peut plus
    # expliquer la ressemblance ?
    far = distance >= np.quantile(distance, 2 / 3)
    print("\n3. Test décisif — paires politiquement ÉLOIGNÉES (dernier tiers de H)")
    for label, m in (
        ("même département", far & same_dept),
        ("départements différents", far & ~same_dept),
    ):
        rho = pair_correlation(residual, m)
        print(f"  {label:<26s} {int(m.sum()):8d} paires | corrélation {rho:+.3f}")
        rows.append(
            {
                "test": "departement_politiquement_eloignees",
                "groupe": label,
                "paires": int(m.sum()),
                "correlation": rho,
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / "first-round-variogram.csv"
    pl.DataFrame(rows, infer_schema_length=None).write_csv(path)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
