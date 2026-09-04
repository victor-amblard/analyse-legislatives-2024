"""
Sensibilité au prior du *tilt* de remobilisation.

Le tilt $t$ répartit les non-exprimés du premier tour qui se mobilisent au second :
la part du finaliste $k$ est proportionnelle à $s_k^t$. En rapport de forces, $t$
multiplie donc le log-rapport du premier tour, ce qui donne trois repères :
$t=-1$ inverse exactement l'avance, $t=0$ partage à parts égales, $t=1$ reproduit
le rapport de forces.

Les bornes du prior ne sont donc pas un détail de réglage : leur MOYENNE fixe le
comportement supposé par défaut. $\\mathcal U(-1,1)$ suppose une remobilisation
neutre en moyenne ; $\\mathcal U(-1,2)$ suppose qu'elle penche, en moyenne, du côté
du candidat arrivé en tête au premier tour — ce qui, le RN étant en tête dans une
majorité de circonscriptions, n'est pas sans conséquence sur sa projection.

Ce script mesure cette conséquence : mêmes données, même seed, même N, seules les
bornes changent.

Usage :
    python scripts/analyses/tilt_sensitivity.py
    python scripts/analyses/tilt_sensitivity.py --n-simus 200 --model national_anchored
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl

from analyse_legislatives import simulation
from analyse_legislatives.config import DEFAULT_N_SIMUS, DEFAULT_SEED, PROJECT_ROOT
from analyse_legislatives.data import load_full_results, load_second_round_results
from analyse_legislatives.evaluation import energy_score, joint_region_scores
from analyse_legislatives.models import build
from analyse_legislatives.parties import FAMILIES
from analyse_legislatives.projections import winners_by_simulation
from analyse_legislatives.utils.progress import progress_bar

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "publication" / "prior"
FAMILY_LABELS = [str(family) for family in FAMILIES]

# (-1, 1) est le prior retenu ; les deux autres bornent l'espace des choix
# raisonnables : (-1, 2) est l'ancien prior, (-2, 2) élargit symétriquement.
DEFAULT_BOUNDS = ((-1.0, 1.0), (-1.0, 2.0), (-2.0, 2.0))


def run(model_name, bounds, districts, n_simus, seed):
    model = build(model_name, seed=seed, non_expressed_tilt_bounds=bounds)
    with progress_bar(n_simus, f"tilt U{bounds}") as tick:
        return simulation.run(model, districts, n_simus, progress=tick)


def seats(cube, first_round_seats, votes_true):
    winners_sim = winners_by_simulation(cube)
    seats_sim = np.stack(
        [(winners_sim == k).sum(axis=1) for k in range(len(FAMILIES))], axis=1
    ).astype(float)
    winners_true = votes_true.argmax(axis=1)
    seats_true = np.array(
        [(winners_true == k).sum() for k in range(len(FAMILIES))], dtype=float
    )
    for k, family in enumerate(FAMILY_LABELS):
        won = first_round_seats.get(family, 0)
        seats_sim[:, k] += won
        seats_true[k] += won
    return seats_sim, seats_true


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=DEFAULT_N_SIMUS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--model", default="national_anchored")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    first_round = load_full_results()
    actual = load_second_round_results()
    districts = [d for d in first_round.districts if d.circonscription.id in actual]
    ids = [d.circonscription.id for d in districts]
    votes_true = np.array(
        [[actual[i].votes.get(f, 0) for f in FAMILY_LABELS] for i in ids], dtype=float
    )

    rows = []
    print(f"\nmodèle {args.model} | N = {args.n_simus} | seed {args.seed}")
    for bounds in DEFAULT_BOUNDS:
        cube = run(args.model, bounds, districts, args.n_simus, args.seed)
        seats_sim, seats_true = seats(cube, first_round.first_round_seats, votes_true)
        lo, hi = np.quantile(seats_sim, [0.05, 0.95], axis=0)
        _, _, percentile = joint_region_scores(seats_sim, seats_true)
        es = energy_score(seats_sim, seats_true)
        print("\n" + "=" * 70)
        print(
            f"tilt ~ U({bounds[0]:g}, {bounds[1]:g})   moyenne {np.mean(bounds):+.2f}"
            f"   |   ES {es:.2f}   percentile joint {percentile:.1%}"
        )
        print(
            f"  {'parti':>6s} {'réel':>5s} {'médiane':>8s} {'biais':>7s} {'IC 90 %':>16s}"
        )
        for k, party in enumerate(FAMILY_LABELS):
            median = float(np.median(seats_sim[:, k]))
            print(
                f"  {party:>6s} {seats_true[k]:5.0f} {median:8.0f} "
                f"{median - seats_true[k]:+7.0f}   [{lo[k]:4.0f} — {hi[k]:4.0f}]"
            )
            rows.append(
                {
                    "modele": args.model,
                    "tilt_min": bounds[0],
                    "tilt_max": bounds[1],
                    "parti": party,
                    "reel": seats_true[k],
                    "mediane": median,
                    "biais": median - seats_true[k],
                    "p05": lo[k],
                    "p95": hi[k],
                    "largeur": hi[k] - lo[k],
                    "energy_score": es,
                    "percentile_joint": percentile,
                }
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / "tilt-sensitivity.csv"
    pl.DataFrame(rows).write_csv(path)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
