"""
Prédictive a priori de la matrice de report : qu'implique réellement le modèle
ordinal sur les taux ?

Le modèle ne fixe aucun taux moyen. Il déclare des ordres de préférence et tire
une concentration nationale log-uniformément entre 0.5 et 1 à chaque simulation.
Ce script montre la distribution impliquée ; les scénarios à alpha fixe sont traités séparément
par ``scripts/analyses/alpha_sensitivity.py``.

Deux quantités sont rapportées par cellule :

- **marginale** — la loi du taux d'une circonscription quelconque. Elle décrit ce
  que le modèle croit *a priori* sur un report donné.
- **dispersion locale** — l'écart-type du taux entre circonscriptions, à
  simulation fixée. Elle mesure l'hétérogénéité que chaque variante s'autorise :
  nulle par construction pour `national`, croissante ensuite.

Usage :
    python scripts/analyses/prior_predictive.py                        # variante par défaut
    python scripts/analyses/prior_predictive.py --model national
    python scripts/analyses/prior_predictive.py --compare              # les 3 variantes
    python scripts/analyses/prior_predictive.py --csv out.csv
"""

from collections.abc import Mapping
import argparse
from pathlib import Path

import numpy as np
import polars as pl

from analyse_legislatives import simulation
from analyse_legislatives.data import load_full_results
from analyse_legislatives.config import DEFAULT_N_SIMUS, DEFAULT_SEED
from analyse_legislatives.models import (
    DEFAULT_MODEL,
    PUBLICATION_MODELS,
    STOCHASTIC_MODELS,
    build,
)
from analyse_legislatives.parties import label

QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]


def summarize(model_name: str, districts, n_simus: int, seed: int) -> pl.DataFrame:
    """Un tableau par cellule : quantiles de la marginale, et dispersion locale."""
    model = build(model_name, seed=seed)
    marginal, spread = simulation.prior_predictive_rates(model, districts, n_simus)
    cells = model.matrix_cells

    quantiles = np.quantile(marginal, QUANTILES, axis=0)
    return pl.DataFrame(
        {
            "cellule": [f"{label(s)}->{label(t)}" for s, t in cells],
            "p05": quantiles[0],
            "p25": quantiles[1],
            "mediane": quantiles[2],
            "p75": quantiles[3],
            "p95": quantiles[4],
            "largeur_ic90": quantiles[4] - quantiles[0],
            "dispersion_locale": spread.mean(axis=0),
        }
    )


def print_single(model_name: str, table: pl.DataFrame, n_simus: int) -> None:
    print("\n" + "=" * 88)
    print(f"PRÉDICTIVE A PRIORI — modèle « {model_name} », N = {n_simus} tirages")
    print("=" * 88)
    print(table.with_columns(pl.exclude("cellule").round(3)))
    print(
        "\nLecture : « médiane » n'est PAS un taux moyen choisi — c'est ce que l'ordre "
        "déclaré implique. Un intervalle large signale une cellule que l'ordre ne "
        "contraint presque pas ; « dispersion_locale » est l'écart-type entre "
        "circonscriptions à simulation fixée (0 = aucune variation locale)."
    )
    widest = table.sort("largeur_ic90", descending=True).row(0, named=True)
    tightest = table.sort("largeur_ic90").row(0, named=True)
    print(
        f"\nCellule la moins contrainte : {widest['cellule']} "
        f"(IC90 large de {widest['largeur_ic90']:.3f})"
        f"\nCellule la plus contrainte  : {tightest['cellule']} "
        f"(IC90 large de {tightest['largeur_ic90']:.3f})"
    )


def print_comparison(tables: Mapping[str, pl.DataFrame], n_simus: int) -> None:
    print("\n" + "=" * 88)
    print(f"COMPARAISON DES VARIANTES — N = {n_simus} tirages")
    print("=" * 88)

    medians = None
    for name, table in tables.items():
        values = table.select("cellule", pl.col("mediane").alias(name))
        medians = values if medians is None else medians.join(values, on="cellule")
    if medians is None:
        raise ValueError("aucune table à comparer")
    print("\n--- Médiane de la marginale par cellule ---")
    print(medians.with_columns(pl.exclude("cellule").round(3)))
    print(
        "\nCes colonnes doivent être proches : les trois variantes partagent les "
        "mêmes ordres de préférence, donc la même marginale nationale. Elles ne "
        "diffèrent que par la STRUCTURE de la variation locale."
    )

    print("\n--- Ce qui distingue réellement les variantes ---")
    summary = pl.DataFrame(
        [
            {
                "modele": name,
                "largeur IC90 moyenne": table["largeur_ic90"].mean(),
                "dispersion locale moyenne": table["dispersion_locale"].mean(),
            }
            for name, table in tables.items()
        ]
    )
    print(summary.with_columns(pl.exclude("modele").round(4)))
    print(
        "\nLecture : `national` et `national_anchored` partagent une matrice "
        "nationale ; `kernel_anchored` autorise une dispersion locale corrélée "
        "entre circonscriptions politiquement proches au sens de Hellinger."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", choices=list(STOCHASTIC_MODELS), default=DEFAULT_MODEL
    )
    parser.add_argument("--n-simus", type=int, default=DEFAULT_N_SIMUS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--compare", action="store_true", help="tourner les 3 variantes et les comparer"
    )
    parser.add_argument("--csv", type=Path, help="écrit le détail par cellule")
    args = parser.parse_args()

    districts = load_full_results().districts
    print(
        f"{len(districts)} circonscriptions, prédictive a priori (aucune donnée de 2nd tour)."
    )

    names = list(PUBLICATION_MODELS) if args.compare else [args.model]
    tables = {}
    for name in names:
        tables[name] = summarize(name, districts, args.n_simus, args.seed)
        if not args.compare:
            print_single(name, tables[name], args.n_simus)

    if args.compare:
        print_comparison(tables, args.n_simus)

    if args.csv:
        combined = pl.concat(
            [
                table.with_columns(pl.lit(name).alias("modele"))
                for name, table in tables.items()
            ]
        )
        combined.write_csv(args.csv)
        print(f"\nDétail écrit dans {args.csv}")


if __name__ == "__main__":
    main()
