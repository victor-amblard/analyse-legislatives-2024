"""Sensibilité croisée des sièges à la bande passante et au poids national.

Cette expérience ne calibre aucun paramètre sur le second tour. Elle fixe lambda
sur une grille et multiplie la bande passante médiane par plusieurs facteurs,
puis résume la prédictive a priori des sièges. Le modèle publié reste inchangé :
il tire lambda dans Beta(2, 2) à chaque simulation.
"""

import argparse
from pathlib import Path

import polars as pl

from analyse_legislatives import simulation
from analyse_legislatives.config import DEFAULT_SEED, PROJECT_ROOT
from analyse_legislatives.data import load_full_results
from analyse_legislatives.models import KernelModel, build
from analyse_legislatives.utils.progress import progress_bar
from analyse_legislatives.projections import seats_by_simulation

DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts/publication/sensitivity/kernel-h-lambda.csv"
DEFAULT_BANDWIDTH_MULTIPLIERS = (0.25, 0.5, 1.0, 2.0)
DEFAULT_MIXING_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)


def summarize_scenario(
    seats: pl.DataFrame, bandwidth_multiplier: float, mixing_weight: float
) -> list[dict]:
    """Une ligne de quantiles par parti pour une cellule de la grille."""
    rows = []
    for party in seats.columns:
        values = seats[party]
        p05, p95 = values.quantile(0.05), values.quantile(0.95)
        if p05 is None or p95 is None:
            raise ValueError(f"quantiles indéfinis pour {party} : série vide")
        rows.append(
            {
                "bandwidth_multiplier": bandwidth_multiplier,
                "mixing_weight": mixing_weight,
                "party": party,
                "mean": values.mean(),
                "sd": values.std(),
                "p05": p05,
                "p95": p95,
                "width90": p95 - p05,
                "simulations": len(values),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=300)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--bandwidth-multipliers",
        type=float,
        nargs="+",
        default=DEFAULT_BANDWIDTH_MULTIPLIERS,
    )
    parser.add_argument(
        "--mixing-weights",
        type=float,
        nargs="+",
        default=DEFAULT_MIXING_WEIGHTS,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if args.n_simus < 20:
        parser.error("--n-simus doit être au moins 20 pour estimer les quantiles.")
    if any(not 0 <= weight <= 1 for weight in args.mixing_weights):
        parser.error("les poids de mélange doivent appartenir à [0, 1].")
    if any(multiplier <= 0 for multiplier in args.bandwidth_multipliers):
        parser.error("les multiplicateurs de bande passante doivent être positifs.")

    first_round = load_full_results()
    probe = build("kernel_anchored", seed=args.seed)
    if not isinstance(probe, KernelModel):
        raise TypeError("cette analyse exige une variante à noyau")
    default_bandwidth = probe.kernel_bandwidth_for(first_round.districts)
    rows = []
    national_rows = None

    for weight in args.mixing_weights:
        # À lambda=1, le champ local disparaît : h n'a mathématiquement aucun
        # effet. Une seule simulation suffit, puis le résultat est recopié sur
        # les colonnes de la grille au lieu de refaire le même calcul.
        multipliers = (
            [args.bandwidth_multipliers[0]]
            if weight == 1
            else args.bandwidth_multipliers
        )
        for multiplier in multipliers:
            model = build(
                "kernel_anchored",
                seed=args.seed,
                kernel_bandwidth=default_bandwidth * multiplier,
                mixing_weight=weight,
            )
            label = f"h×{multiplier:g}, lambda={weight:g}"
            with progress_bar(args.n_simus, label) as tick:
                cube = simulation.run(
                    model, first_round.districts, args.n_simus, progress=tick
                )
            seats = seats_by_simulation(cube, first_round.first_round_seats)
            scenario_rows = summarize_scenario(seats, multiplier, weight)
            rows.extend(scenario_rows)
            if weight == 1:
                national_rows = scenario_rows
            print(f"h×{multiplier:g}, lambda={weight:g}: terminé")

        if weight == 1 and national_rows is not None:
            source_multiplier = args.bandwidth_multipliers[0]
            for multiplier in args.bandwidth_multipliers[1:]:
                rows.extend(
                    [
                        row
                        | {
                            "bandwidth_multiplier": multiplier,
                            "mixing_weight": 1.0,
                        }
                        for row in national_rows
                        if row["bandwidth_multiplier"] == source_multiplier
                    ]
                )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(args.output)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
