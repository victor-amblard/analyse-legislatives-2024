"""
Ce que change la LOCALISATION du tilt dans le modèle à noyau.

Depuis `KernelModel.tilts_for_districts`, le tilt de remobilisation est tiré comme
les taux de report : un champ latent gaussien mélangeant une composante nationale
et une composante locale corrélée par le noyau de Hellinger, puis ramené sur
`U(bornes)` par transformation inverse. Sa loi marginale est donc inchangée ;
seule la dépendance entre circonscriptions l'est.

Ce script mesure l'effet de ce seul changement : même modèle, même seed, même N,
avec d'un côté le tilt national d'avant (une valeur pour la France entière) et de
l'autre le tilt localisé.

Attention au SENS attendu : une variation localisée se compense partiellement à
l'agrégation nationale, donc les intervalles de sièges doivent plutôt se
RESSERRER. Le gain n'est réel que si la couverture ne se dégrade pas en même
temps — la couverture des scores par circonscription est déjà trop confiante.

Usage :
    python scripts/analyses/local_tilt_effect.py
    python scripts/analyses/local_tilt_effect.py --n-simus 200
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl

from ordering_sensitivity import FAMILY_LABELS, evaluate

from analyse_legislatives import simulation
from analyse_legislatives.config import DEFAULT_N_SIMUS, DEFAULT_SEED, PROJECT_ROOT
from analyse_legislatives.data import load_full_results, load_second_round_results
from analyse_legislatives.models import build
from analyse_legislatives.models.base import Model
from analyse_legislatives.utils.progress import progress_bar

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "publication" / "prior"


def simulate(model_name, districts, n_simus, seed, *, local_tilt: bool):
    """Le modèle publié, éventuellement ramené au tilt national d'avant.

    `Model.tilts_for_districts` est l'implémentation nationale (une valeur
    diffusée partout) : la relier à l'instance restaure exactement le
    comportement précédent, sans dupliquer le reste du modèle.
    """
    model = build(model_name, seed=seed)
    if not local_tilt:
        # Rebrancher une méthode sur l'instance est exactement l'objet de ce
        # script ; mypy l'interdit par défaut, à raison, mais ici c'est le
        # dispositif expérimental lui-même. `local_components_effect.py` fait de
        # même sans être signalé : sa `simulate` n'est pas annotée, donc mypy
        # n'inspecte pas son corps.
        model.tilts_for_districts = Model.tilts_for_districts.__get__(  # type: ignore[method-assign]
            model
        )
    label = f"{model_name} tilt {'local' if local_tilt else 'national'}"
    with progress_bar(n_simus, label) as tick:
        return simulation.run(model, districts, n_simus, progress=tick)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=DEFAULT_N_SIMUS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--model", default="kernel_anchored")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    first_round = load_full_results()
    actual = load_second_round_results()
    districts = [d for d in first_round.districts if d.circonscription.id in actual]
    ids = [d.circonscription.id for d in districts]
    votes_true = np.array(
        [[actual[i].votes.get(f, 0) for f in FAMILY_LABELS] for i in ids], dtype=float
    )
    exprimes_true = np.array([actual[i].exprimes for i in ids], dtype=float)

    results = {}
    for variant, local in (("national", False), ("local", True)):
        cube = simulate(
            args.model, districts, args.n_simus, args.seed, local_tilt=local
        )
        results[variant] = evaluate(
            cube, first_round.first_round_seats, votes_true, exprimes_true
        )

    a, b = results["national"], results["local"]
    print("\n" + "=" * 78)
    print(f"MODÈLE {args.model} — tilt national  ->  tilt localisé par le noyau")
    print("=" * 78)
    print(f"\n  {'parti':>6s} {'réel':>5s} {'tilt national':>26s} {'tilt local':>26s}")
    for party in a["per_party"]:
        pa, pb = a["per_party"][party], b["per_party"][party]
        print(
            f"  {party:>6s} {pa['reel']:5.0f}"
            f"   [{pa['p05']:4.0f} — {pa['p95']:4.0f}] méd {pa['mediane']:4.0f}"
            f"   [{pb['p05']:4.0f} — {pb['p95']:4.0f}] méd {pb['mediane']:4.0f}"
        )
    for label, key, fmt in (
        ("largeur moyenne (sièges)", "largeur_moyenne_sieges", "{:.1f}"),
        ("partis couverts (IC 90 %, /7)", "partis_couverts", "{:.0f}"),
        ("energy score (sièges)", "energy_score", "{:.2f}"),
        ("percentile joint du réel", "percentile_joint", "{:.1%}"),
        ("couverture scores (nom. 90 %)", "couverture_scores_90", "{:.1%}"),
        ("largeur scores (pts)", "largeur_scores_90", "{:.2f}"),
        ("vainqueur local correct", "vainqueur_correct", "{:.1%}"),
    ):
        print(
            f"\n  {label:<30s} {fmt.format(a[key]):>10s}  ->{fmt.format(b[key]):>10s}"
        )

    rows = [
        {"modele": args.model, "tilt": variant}
        | {k: v for k, v in res.items() if k != "per_party"}
        for variant, res in results.items()
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / "local-tilt-effect.csv"
    pl.DataFrame(rows).write_csv(path)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
