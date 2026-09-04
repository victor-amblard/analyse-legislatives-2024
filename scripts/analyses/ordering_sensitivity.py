"""
Que coûte — et que rapporte — un ORDRE TOTAL de préférences ?

Le billet affirme que l'essentiel de la largeur des intervalles vient du flou des
préférences : plusieurs destinations laissées ex aequo, dont l'ordre relatif est
retiré à chaque simulation. Ce script mesure l'affirmation au lieu de la
supposer. Il relance les mêmes modèles, à seed et N identiques, en remplaçant
l'ordre PARTIEL de `config/model.yaml` par un ordre TOTAL déclaré ci-dessous.

Rien d'autre ne change : mêmes priors, mêmes données, même chemin de code que
`scripts/evaluate.py`. L'écart mesuré est donc imputable au seul ordre.

Deux quantités comptent, et il faut les lire ensemble (cf. « calibration et
finesse » du billet) :
  - la LARGEUR des intervalles de sièges — ce que l'ordre total est censé gagner ;
  - la COUVERTURE et l'energy score — ce qu'il peut coûter si l'ordre est faux.

Un ordre total qui resserre les intervalles tout en dégradant la couverture n'est
pas un progrès : c'est exactement la « fausse précision » que le billet reproche
aux fourchettes publiées.

Usage :
    python scripts/analyses/ordering_sensitivity.py
    python scripts/analyses/ordering_sensitivity.py --n-simus 200 --models national_anchored
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl

from analyse_legislatives import simulation
from analyse_legislatives.config import (
    DEFAULT_N_SIMUS,
    DEFAULT_SEED,
    PROJECT_ROOT,
)
from analyse_legislatives.data import load_full_results, load_second_round_results
from analyse_legislatives.evaluation import (
    coverage_and_width,
    energy_score,
    joint_region_scores,
)
from analyse_legislatives.models import PUBLICATION_MODELS, build
from analyse_legislatives.parties import (
    FAMILIES,
    NON_EXPRIMES,
    PoliticalFamily as P,
)
from analyse_legislatives.projections import winners_by_simulation
from analyse_legislatives.utils.progress import progress_bar

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "publication" / "prior"

FAMILY_LABELS = [str(family) for family in FAMILIES]

# Ordre TOTAL testé : un palier par destination, donc aucune paire ex aequo.
# `DIV` reste sans ordre déclaré (un seul palier) : le billet ne prétend rien sur
# les préférences des divers, et l'inventer ici brouillerait la comparaison.
TOTAL_ORDERINGS = {
    P.NFPx: [P.DVG, P.ENSx, P.DIV, P.DVD, P.LR, NON_EXPRIMES, P.RNx],
    P.DVG: [P.NFPx, P.ENSx, P.DIV, P.DVD, P.LR, NON_EXPRIMES, P.RNx],
    P.ENSx: [P.DVG, P.NFPx, P.DVD, P.LR, P.DIV, NON_EXPRIMES, P.RNx],
    P.DVD: [P.LR, P.ENSx, P.DVG, P.NFPx, P.DIV, P.RNx, NON_EXPRIMES],
    P.LR: [P.DVD, P.ENSx, P.DVG, P.NFPx, P.DIV, P.RNx, NON_EXPRIMES],
    P.RNx: [P.LR, P.DVD, P.ENSx, P.DVG, P.DIV, NON_EXPRIMES, P.NFPx],
}


def total_ordering_config() -> tuple[dict, tuple]:
    """Un palier par destination, et plus aucune destination libre.

    `free_targets` doit être vidé : `DIV` devient une destination ordonnée dans
    six des sept lignes, et `Model.__post_init__` refuse — à raison — qu'une
    destination soit à la fois libre et ordonnée.
    """
    orderings = {
        source: [[target] for target in order]
        for source, order in TOTAL_ORDERINGS.items()
    }
    # La ligne DIV garde son unique palier : aucun ordre déclaré.
    orderings[P.DIV] = [
        [target for target in (*FAMILIES, NON_EXPRIMES) if target != P.DIV]
    ]
    return orderings, ()


def simulate(model_name: str, orderings, free_targets, districts, n_simus, seed):
    """Même chemin de code que `scripts/evaluate.py`, orderings mis à part."""
    kwargs = {}
    if orderings is not None:
        kwargs = {"transfer_orderings": orderings, "free_targets": free_targets}
    model = build(model_name, seed=seed, **kwargs)
    label = f"{model_name} ({'total' if orderings else 'partiel'})"
    with progress_bar(n_simus, label) as tick:
        return simulation.run(model, districts, n_simus, progress=tick)


def national_seats(cube, first_round_seats, votes_true):
    """Sièges simulés et sièges réels, premier tour inclus (cf. evaluate.py)."""
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


def evaluate(cube, first_round_seats, votes_true, exprimes_true):
    """Les quatre chiffres qui décident : largeur, couverture, ES, région jointe."""
    seats_sim, seats_true = national_seats(cube, first_round_seats, votes_true)

    lo, hi = np.quantile(seats_sim, [0.05, 0.95], axis=0)
    widths = hi - lo
    inside = (seats_true >= lo) & (seats_true <= hi)

    _, observed_score, percentile = joint_region_scores(seats_sim, seats_true)

    party_cube = cube[:, :, : len(FAMILIES)]
    exprimes_sim = party_cube.sum(axis=2)
    share_sim = np.where(
        exprimes_sim[:, :, None] > 0,
        party_cube / np.maximum(exprimes_sim, 1)[:, :, None] * 100,
        0.0,
    )
    share_true = votes_true / exprimes_true[:, None] * 100
    d_idx, p_idx = np.nonzero(votes_true > 0)
    score_cov, score_width = coverage_and_width(
        share_sim[:, d_idx, p_idx], share_true[d_idx, p_idx], 0.90
    )

    winners_sim = winners_by_simulation(cube)
    winner_true = votes_true.argmax(axis=1)
    winner_accuracy = float((winners_sim == winner_true[None, :]).mean())

    return {
        "per_party": {
            FAMILY_LABELS[k]: {
                "reel": seats_true[k],
                "p05": lo[k],
                "mediane": float(np.median(seats_sim[:, k])),
                "p95": hi[k],
                "largeur": widths[k],
                "dans_ic90": bool(inside[k]),
            }
            for k in range(len(FAMILIES))
        },
        "largeur_moyenne_sieges": float(widths.mean()),
        "partis_couverts": int(inside.sum()),
        "energy_score": energy_score(seats_sim, seats_true),
        "percentile_joint": percentile,
        "score_joint": observed_score,
        "couverture_scores_90": score_cov,
        "largeur_scores_90": score_width,
        "vainqueur_correct": winner_accuracy,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=DEFAULT_N_SIMUS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--models", nargs="+", default=list(PUBLICATION_MODELS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    first_round = load_full_results()
    actual = load_second_round_results()
    districts = [d for d in first_round.districts if d.circonscription.id in actual]
    ids = [district.circonscription.id for district in districts]
    votes_true = np.array(
        [[actual[i].votes.get(f, 0) for f in FAMILY_LABELS] for i in ids], dtype=float
    )
    exprimes_true = np.array([actual[i].exprimes for i in ids], dtype=float)

    total_orderings, total_free = total_ordering_config()
    variants = {
        "partiel": (None, ()),
        "total": (total_orderings, total_free),
    }

    rows = []
    per_party_rows = []
    for model_name in args.models:
        results = {}
        for variant, (orderings, free_targets) in variants.items():
            cube = simulate(
                model_name,
                orderings,
                free_targets,
                districts,
                args.n_simus,
                args.seed,
            )
            results[variant] = evaluate(
                cube, first_round.first_round_seats, votes_true, exprimes_true
            )
            for party, stats in results[variant]["per_party"].items():
                per_party_rows.append(
                    {"modele": model_name, "ordre": variant, "parti": party, **stats}
                )
            rows.append(
                {
                    "modele": model_name,
                    "ordre": variant,
                    **{k: v for k, v in results[variant].items() if k != "per_party"},
                }
            )
        report(model_name, results)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "ordering-sensitivity.csv"
    party_path = args.output_dir / "ordering-sensitivity-by-party.csv"
    pl.DataFrame(rows).write_csv(summary_path)
    pl.DataFrame(per_party_rows).write_csv(party_path)
    print(f"\nwrote {summary_path}")
    print(f"wrote {party_path}")


def report(model_name: str, results: dict) -> None:
    partiel, total = results["partiel"], results["total"]
    print("\n" + "=" * 78)
    print(f"MODÈLE {model_name}")
    print("=" * 78)
    print(
        f"\n  {'parti':>6s} {'réel':>5s} "
        + "  ".join(f"{h:>21s}" for h in ("ordre partiel", "ordre total"))
        + f" {'Δ largeur':>10s}"
    )
    for party in partiel["per_party"]:
        a, b = partiel["per_party"][party], total["per_party"][party]
        print(
            f"  {party:>6s} {a['reel']:5.0f} "
            f"  [{a['p05']:4.0f}—{a['p95']:4.0f}] méd {a['mediane']:4.0f}"
            f"  [{b['p05']:4.0f}—{b['p95']:4.0f}] méd {b['mediane']:4.0f}"
            f" {b['largeur'] - a['largeur']:+10.0f}"
        )
    print(
        f"\n  largeur moyenne (sièges)      : {partiel['largeur_moyenne_sieges']:6.1f}"
        f"  ->{total['largeur_moyenne_sieges']:7.1f}"
        f"   ({total['largeur_moyenne_sieges'] / partiel['largeur_moyenne_sieges'] - 1:+.0%})"
    )
    print(
        f"  partis couverts (IC 90 %, /7) : {partiel['partis_couverts']:6d}"
        f"  ->{total['partis_couverts']:7d}"
    )
    print(
        f"  energy score (sièges)         : {partiel['energy_score']:6.2f}"
        f"  ->{total['energy_score']:7.2f}"
    )
    print(
        f"  percentile joint du réel      : {partiel['percentile_joint']:6.1%}"
        f"  ->{total['percentile_joint']:7.1%}"
    )
    print(
        f"  couverture scores (nom. 90 %) : {partiel['couverture_scores_90']:6.1%}"
        f"  ->{total['couverture_scores_90']:7.1%}"
    )
    print(
        f"  largeur scores (pts)          : {partiel['largeur_scores_90']:6.2f}"
        f"  ->{total['largeur_scores_90']:7.2f}"
    )
    print(
        f"  vainqueur local correct       : {partiel['vainqueur_correct']:6.1%}"
        f"  ->{total['vainqueur_correct']:7.1%}"
    )


if __name__ == "__main__":
    main()
