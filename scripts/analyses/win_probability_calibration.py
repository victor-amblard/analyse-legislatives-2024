"""
Courbe de calibration des probabilités de victoire, au niveau circonscription.

`scripts/evaluate.py` publie déjà cette calibration, mais en 5 tranches larges
imprimées en texte (« calibration des probabilités de victoire »). Ce script
reprend EXACTEMENT la même définition — probabilité de victoire simulée par
parti et par circonscription, restreinte aux partis réellement en lice — mais
en déciles, pour tracer une vraie courbe fiabilité (prédit / réalisé) plutôt que
cinq points.

Comme dans evaluate.py : les cellules (circonscription, parti) où le parti
n'est pas sur le bulletin sont EXCLUES avant le binning, pas seulement mises à
zéro — sinon la tranche 0-10 % se remplit de zéros structurels qui ne mesurent
rien du modèle.

IMPORTANT — les résultats du 2nd tour ne servent qu'ici, en mesure. C'est une
évaluation a posteriori, comme le reste de scripts/evaluate.py.

Usage :
    python scripts/analyses/win_probability_calibration.py
    python scripts/analyses/win_probability_calibration.py --n-simus 500 --n-bins 8
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl

from analyse_legislatives import simulation
from analyse_legislatives.config import DEFAULT_N_SIMUS, DEFAULT_SEED, PROJECT_ROOT
from analyse_legislatives.data import load_full_results, load_second_round_results
from analyse_legislatives.models import DEFAULT_MODEL, build
from analyse_legislatives.parties import DESTINATION_LABELS, FAMILIES
from analyse_legislatives.projections import winners_by_simulation
from analyse_legislatives.utils.progress import progress_bar

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "publication" / "sensitivity"
FAMILY_LABELS = DESTINATION_LABELS[: len(FAMILIES)]
DEFAULT_N_BINS = 10
MIN_BIN_SIZE = 15
"""En deçà, l'intervalle de confiance binomial est trop large pour qu'un point
signifie quoi que ce soit ; la tranche est fusionnée avec sa voisine plutôt
qu'affichée telle quelle."""


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """IC de Wilson à ~95 % pour une proportion — préféré à l'approximation
    normale ici car plusieurs tranches ont un `n` modeste (quelques dizaines) et
    des taux proches de 0 ou 1, où l'intervalle normal peut sortir de [0, 1]."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return ((centre - half) / denom, (centre + half) / denom)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=DEFAULT_N_SIMUS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--n-bins", type=int, default=DEFAULT_N_BINS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    first_round = load_full_results()
    actual = load_second_round_results()
    districts = [d for d in first_round.districts if d.circonscription.id in actual]
    ids = [d.circonscription.id for d in districts]
    votes_true = np.array(
        [[actual[i].votes.get(f, 0) for f in FAMILY_LABELS] for i in ids], dtype=float
    )
    winners_true = votes_true.argmax(axis=1)
    qualified = votes_true > 0

    model = build(args.model, seed=args.seed)
    with progress_bar(args.n_simus, args.model) as tick:
        cube = simulation.run(model, districts, args.n_simus, progress=tick)
    winners_sim = winners_by_simulation(cube)

    win_prob = np.stack(
        [(winners_sim == k).mean(axis=0) for k in range(len(FAMILIES))], axis=1
    )
    won = np.eye(len(FAMILIES))[winners_true].astype(bool)

    # Restreint aux cellules (circonscription, parti) où le parti est qualifié —
    # même exclusion que evaluate.py, pour la même raison (voir le docstring).
    p = win_prob[qualified]
    y = won[qualified]

    order = np.argsort(p)
    p, y = p[order], y[order]
    n_total = len(p)

    # Tranches à effectif égal (déciles de la probabilité prédite), pas à largeur
    # égale : la masse est très inégale (beaucoup de probabilités proches de 0 ou
    # de 1), des tranches à largeur fixe laisseraient des tranches médianes vides.
    edges = np.unique(
        np.quantile(p, np.linspace(0, 1, args.n_bins + 1), method="lower")
    )
    bin_id = np.searchsorted(edges, p, side="right") - 1
    bin_id = np.clip(bin_id, 0, len(edges) - 2)

    rows = []
    pending: list[int] = []
    for b in range(len(edges) - 1):
        pending.append(b)
        mask = np.isin(bin_id, pending)
        n = int(mask.sum())
        if n < MIN_BIN_SIZE and b < len(edges) - 2:
            continue  # fusionne avec la tranche suivante
        successes = int(y[mask].sum())
        lo, hi = wilson_interval(successes, n)
        rows.append(
            {
                "predit_moyen": float(p[mask].mean()),
                "predit_min": float(p[mask].min()),
                "predit_max": float(p[mask].max()),
                "realise": successes / n,
                "ic95_bas": lo,
                "ic95_haut": hi,
                "n": n,
            }
        )
        pending = []

    table = pl.DataFrame(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f"win-probability-calibration-{args.model}.csv"
    table.write_csv(path)

    print(
        f"\n{n_total} cellules (circonscription, parti qualifié) — modèle {args.model}\n"
    )
    print(f"  {'prédit':>16s} {'réalisé':>9s} {'IC95%':>17s} {'n':>6s}")
    for row in table.iter_rows(named=True):
        print(
            f"  [{row['predit_min']:.0%}–{row['predit_max']:.0%}]".rjust(16)
            + f" {row['realise']:9.1%} [{row['ic95_bas']:5.1%};{row['ic95_haut']:5.1%}]"
            f" {row['n']:6d}"
        )
    ece = float(
        (table["n"] * (table["predit_moyen"] - table["realise"]).abs()).sum() / n_total
    )
    print(f"\n  erreur de calibration moyenne (pondérée par n) : {ece:.1%}")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
