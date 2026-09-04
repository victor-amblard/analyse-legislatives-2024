"""
Que localise-t-on vraiment dans le modèle à noyau ?

`KernelModel` corrèle les cellules des lignes de report entre circonscriptions.
Deux quantités échappaient à cette localisation, alors qu'elles relèvent de la
même hypothèse 6 :

- le **tilt** de remobilisation, qui oriente le plus gros réservoir de voix ;
- l'**ordre** lui-même, c'est-à-dire le tirage qui départage les destinations
  laissées ex aequo — la principale source d'incertitude du modèle.

Les deux sont désormais localisables. Ce script mesure leur contribution
séparément et conjointement, à modèle, seed et N identiques : seule la structure
de dépendance change, jamais les lois marginales.

Lecture attendue : localiser une variation la fait partiellement se compenser à
l'agrégation nationale, donc les intervalles de sièges devraient se resserrer. Le
resserrement n'est un progrès que si la couverture tient — d'où les colonnes de
calibration à côté des largeurs.

Usage :
    python scripts/analyses/local_components_effect.py
    python scripts/analyses/local_components_effect.py --n-simus 200
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
from analyse_legislatives.models.copula import CopulaModel
from analyse_legislatives.utils.progress import progress_bar

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "publication" / "prior"

VARIANTS = {
    "aucun": (False, False),
    "tilt seul": (True, False),
    "ordre seul": (False, True),
    "tilt + ordre": (True, True),
}


def simulate(model_name, districts, n_simus, seed, *, local_tilt, local_order):
    """Le modèle publié, ramené au comportement national sur les axes désactivés.

    Relier l'implémentation de la classe de base à l'instance restaure exactement
    le comportement d'avant la localisation, sans dupliquer le modèle.
    """
    model = build(model_name, seed=seed)
    if not local_tilt:
        model.tilts_for_districts = Model.tilts_for_districts.__get__(model)
    if not local_order:
        model._local_extension_ranks = CopulaModel._local_extension_ranks.__get__(model)
    label = f"tilt {'L' if local_tilt else 'N'} / ordre {'L' if local_order else 'N'}"
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
    for name, (local_tilt, local_order) in VARIANTS.items():
        cube = simulate(
            args.model,
            districts,
            args.n_simus,
            args.seed,
            local_tilt=local_tilt,
            local_order=local_order,
        )
        results[name] = evaluate(
            cube, first_round.first_round_seats, votes_true, exprimes_true
        )

    print("\n" + "=" * 86)
    print(f"MODÈLE {args.model} — ce qui est localisé par le noyau")
    print("=" * 86)
    header = f"  {'mesure':<32s}" + "".join(f"{name:>13s}" for name in VARIANTS)
    print("\n" + header)
    for label, key, fmt in (
        ("largeur moyenne (sièges)", "largeur_moyenne_sieges", "{:.1f}"),
        ("partis couverts (IC 90 %, /7)", "partis_couverts", "{:.0f}"),
        ("energy score (sièges)", "energy_score", "{:.2f}"),
        ("percentile joint du réel", "percentile_joint", "{:.1%}"),
        ("couverture scores (nom. 90 %)", "couverture_scores_90", "{:.1%}"),
        ("largeur scores (pts)", "largeur_scores_90", "{:.2f}"),
        ("proba moyenne vrai vainqueur", "vainqueur_correct", "{:.1%}"),
    ):
        cells = "".join(f"{fmt.format(results[n][key]):>13s}" for n in VARIANTS)
        print(f"  {label:<32s}{cells}")

    print(f"\n  {'parti':>6s} {'réel':>5s}" + "".join(f"{n:>21s}" for n in VARIANTS))
    for party in FAMILY_LABELS:
        cells = "".join(
            f"   [{results[n]['per_party'][party]['p05']:4.0f}—"
            f"{results[n]['per_party'][party]['p95']:4.0f}]"
            f" {results[n]['per_party'][party]['mediane']:4.0f}"
            for n in VARIANTS
        )
        print(
            f"  {party:>6s} {results['aucun']['per_party'][party]['reel']:5.0f}{cells}"
        )

    rows = [
        {"modele": args.model, "localisation": name}
        | {k: v for k, v in res.items() if k != "per_party"}
        for name, res in results.items()
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / "local-components-effect.csv"
    pl.DataFrame(rows).write_csv(path)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
