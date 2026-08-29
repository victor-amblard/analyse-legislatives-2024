"""Analyse ex ante de sensibilité à la concentration de la Dirichlet.

Les scénarios ne sont comparés à aucun résultat du second tour. Le script produit
deux tables utilisées par les figures du write-up : distribution nationale des
sièges selon alpha, et sièges conditionnels aux non-exprimés simulés pour alpha=1.

Usage :
    python scripts/analyses/alpha_sensitivity.py
    python scripts/analyses/alpha_sensitivity.py --n-simus 5000
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl

from analyse_legislatives import simulation
from analyse_legislatives.data import load_full_results
from analyse_legislatives.config import DEFAULT_SEED
from analyse_legislatives.models import build
from analyse_legislatives.utils.progress import progress_bar
from analyse_legislatives.config import PROJECT_ROOT
from analyse_legislatives.projections import (
    conditional_seats_by_non_expressed,
    expressed_share_by_simulation,
    seats_by_simulation,
)

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "publication" / "prior"
DEFAULT_ALPHAS = (0.5, 1.0, 2.0)


def run_scenario(alpha: float, n_simus: int, first_round):
    """Simule un scénario de concentration, toutes les autres hypothèses fixes."""
    model = build(
        "national_anchored",
        seed=DEFAULT_SEED,
        dirichlet_concentration=alpha,
    )
    with progress_bar(n_simus, f"alpha={alpha:g}") as tick:
        cube = simulation.run(model, first_round.districts, n_simus, progress=tick)
    seats = seats_by_simulation(cube, first_round.first_round_seats)
    expressed = expressed_share_by_simulation(
        cube,
        first_round.districts,
        first_round.inscrits_by_id,
    )
    return seats, expressed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=3000)
    parser.add_argument("--alphas", type=float, nargs="+", default=DEFAULT_ALPHAS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    first_round = load_full_results()
    summaries = []
    conditional = None
    for alpha in args.alphas:
        seats, expressed = run_scenario(alpha, args.n_simus, first_round)
        for party in seats.columns:
            values = seats[party].to_numpy()
            summaries.append(
                {
                    "alpha": alpha,
                    "parti": party,
                    "p05": np.quantile(values, 0.05),
                    "mediane": np.median(values),
                    "p95": np.quantile(values, 0.95),
                    "moyenne": values.mean(),
                    "ecart_type": values.std(),
                }
            )
        if alpha == 1:
            conditional = conditional_seats_by_non_expressed(seats, expressed)

    if conditional is None:
        raise ValueError("La liste des scénarios doit contenir alpha=1.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "alpha-sensitivity.csv"
    conditional_path = args.output_dir / "seats-by-non-expressed.csv"
    pl.DataFrame(summaries).write_csv(summary_path)
    conditional.write_csv(conditional_path)
    print(f"wrote {summary_path}")
    print(f"wrote {conditional_path}")


if __name__ == "__main__":
    main()
