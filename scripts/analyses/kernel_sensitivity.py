"""Sensibilité croisée des sièges à la corrélation départementale et à lambda.

Le noyau départemental est en réalité EMBOÎTÉ à deux échelles (région, puis
département dans la région) : voir `KernelModel` pour la construction complète et
`first_round_variogram.py` pour la mesure. Cette grille n'en balaie qu'un axe,
`rho_departement` — appelé `rho` ici par commodité —, croisé avec `lambda`, la
part de variation commune à toute la France. `rho_region` reste fixé à la
moyenne de son prior plutôt que balayé : un cube à trois axes serait plus
coûteux à produire et à lire, pour un paramètre dont l'effet sur l'agrégat
national est structurellement plus faible que celui de `rho_departement` — un
département ne touche qu'environ 1 % des paires de circonscriptions de France,
une région nettement plus, mais `rho_departement` reste le niveau le plus fin
et le plus fortement corrélé mesuré. Aucun paramètre n'est calibré sur le
second tour.

Le modèle publié, lui, tire les trois à chaque simulation. Cette grille sert à
voir ce que `rho_departement` et `lambda` gouvernent isolément, pas à remplacer
ce tirage.
"""

import argparse
from pathlib import Path

import polars as pl

from analyse_legislatives import simulation
from analyse_legislatives.config import (
    DEFAULT_REGION_CORRELATION_PRIOR,
    DEFAULT_SEED,
    PROJECT_ROOT,
)
from analyse_legislatives.data import load_full_results
from analyse_legislatives.models import KernelModel, build
from analyse_legislatives.utils.progress import progress_bar
from analyse_legislatives.projections import seats_by_simulation

DEFAULT_OUTPUT = (
    PROJECT_ROOT / "artifacts/publication/sensitivity/kernel-rho-lambda.csv"
)
DEFAULT_DEPARTMENT_CORRELATIONS = (0.0, 0.25, 0.5, 0.75, 1.0)
REGION_CORRELATION_HELD_AT = DEFAULT_REGION_CORRELATION_PRIOR[0] / sum(
    DEFAULT_REGION_CORRELATION_PRIOR
)
"""Moyenne du prior Beta de `rho_region`, tenue fixe pour cette grille 2D."""
DEFAULT_MIXING_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)


def summarize_scenario(
    seats: pl.DataFrame, department_correlation: float, mixing_weight: float
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
                "department_correlation": department_correlation,
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
        "--department-correlations",
        type=float,
        nargs="+",
        default=DEFAULT_DEPARTMENT_CORRELATIONS,
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
    if any(not 0 <= value <= 1 for value in args.department_correlations):
        parser.error("les corrélations rho doivent appartenir à [0, 1].")

    first_round = load_full_results()
    probe = build("kernel_anchored", seed=args.seed)
    if not isinstance(probe, KernelModel):
        raise TypeError("cette analyse exige une variante à noyau")
    rows = []
    national_rows = None

    for weight in args.mixing_weights:
        # À lambda=1, le champ local disparaît : rho n'a mathématiquement aucun
        # effet. Une seule simulation suffit, puis le résultat est recopié sur
        # les colonnes de la grille au lieu de refaire le même calcul.
        correlations = (
            [args.department_correlations[0]]
            if weight == 1
            else args.department_correlations
        )
        for correlation in correlations:
            model = build(
                "kernel_anchored",
                seed=args.seed,
                department_correlation=correlation,
                # rho_region fixé à la moyenne de son prior : cette grille ne
                # balaie que rho_departement et lambda, voir le docstring.
                region_correlation=REGION_CORRELATION_HELD_AT,
                mixing_weight=weight,
            )
            label = f"rho={correlation:g}, lambda={weight:g}"
            with progress_bar(args.n_simus, label) as tick:
                cube = simulation.run(
                    model, first_round.districts, args.n_simus, progress=tick
                )
            seats = seats_by_simulation(cube, first_round.first_round_seats)
            scenario_rows = summarize_scenario(seats, correlation, weight)
            rows.extend(scenario_rows)
            if weight == 1:
                national_rows = scenario_rows
            print(f"rho={correlation:g}, lambda={weight:g}: terminé")

        if weight == 1 and national_rows is not None:
            source_correlation = args.department_correlations[0]
            for correlation in args.department_correlations[1:]:
                rows.extend(
                    [
                        row
                        | {
                            "department_correlation": correlation,
                            "mixing_weight": 1.0,
                        }
                        for row in national_rows
                        if row["department_correlation"] == source_correlation
                    ]
                )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(args.output)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
