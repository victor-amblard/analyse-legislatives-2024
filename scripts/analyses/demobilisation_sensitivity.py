"""Sensibilité des sièges au taux national de démobilisation des qualifiés.

L'expérience fixe successivement ``d`` sur une grille. Toutes les autres
composantes restent tirées dans leur prior et aucune donnée du second tour
n'intervient. Utiliser la même graine dans chaque scénario limite le bruit de la
comparaison.
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl

from analyse_legislatives import simulation
from analyse_legislatives.config import DEFAULT_SEED, PROJECT_ROOT
from analyse_legislatives.data import load_full_results
from analyse_legislatives.models import build
from analyse_legislatives.projections import seats_by_simulation
from analyse_legislatives.utils.progress import progress_bar

DEFAULT_DEMOBILISATION_RATES = (0.0, 0.05, 0.10, 0.15, 0.20)
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "artifacts/publication/prior/demobilisation-sensitivity.csv"
)


def run_scenario(rate: float, n_simus: int, first_round, seed: int) -> pl.DataFrame:
    model = build(
        "national_anchored",
        seed=seed,
        qualified_demobilisation=rate,
    )
    with progress_bar(n_simus, f"d={rate:.0%}") as tick:
        cube = simulation.run(model, first_round.districts, n_simus, progress=tick)
    return seats_by_simulation(cube, first_round.first_round_seats)


def summarize(rate: float, seats: pl.DataFrame) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for party in seats.columns:
        values = seats[party].to_numpy()
        rows.append(
            {
                "demobilisation": rate,
                "parti": party,
                "p05": float(np.quantile(values, 0.05)),
                "mediane": float(np.median(values)),
                "p95": float(np.quantile(values, 0.95)),
                "moyenne": float(values.mean()),
                "ecart_type": float(values.std()),
                "simulations": len(values),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=2_000)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--rates",
        type=float,
        nargs="+",
        default=DEFAULT_DEMOBILISATION_RATES,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if args.n_simus < 100:
        parser.error("--n-simus doit être au moins 100 pour estimer les quantiles.")
    if any(not 0 <= rate < 1 for rate in args.rates):
        parser.error("les taux de démobilisation doivent appartenir à [0, 1).")

    first_round = load_full_results()
    rows = []
    for rate in args.rates:
        seats = run_scenario(rate, args.n_simus, first_round, args.seed)
        rows.extend(summarize(rate, seats))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(args.output)
    print(f"wrote {args.output.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
