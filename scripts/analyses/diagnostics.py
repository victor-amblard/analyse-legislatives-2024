"""
Diagnostics de fiabilité des projections (aucune donnée externe requise).

Deux questions auxquelles ce script répond :

1. **Erreur Monte-Carlo** — avec N tirages, les quantiles 5%/95% sont eux-mêmes
   estimés avec erreur. On relance avec plusieurs seeds : si les bornes bougent de
   plus de quelques sièges, N est trop faible et une partie de la « variation »
   affichée dans l'app est du bruit d'échantillonnage.

2. **Comparaison des variantes** — les trois variantes partagent les mêmes ordres
   de préférence, donc la même loi nationale des taux ; elles ne diffèrent que par
   la STRUCTURE de la variation locale. Ce que cela change sur les sièges est
   précisément ce qu'on veut mesurer, et il faut le lire à l'aune du bruit
   Monte-Carlo mesuré au point 1 : un écart du même ordre n'est pas interprétable.

Ce que ce script ne fait plus : la sensibilité à `kappa`. Le modèle étant passé en
ORDINAL INTÉGRAL, il n'y a plus de taux moyens fixés à la main ni de paramètre de
concentration autour d'eux — donc plus de sensibilité à mesurer. C'était le
principal aveu du modèle précédent (des intervalles largement déterminés par un
paramètre non calibré) ; il n'a plus lieu d'être.

Attention en revanche à ne pas lire le passage en ordinal comme un gain de
prudence : mesurée par `scripts/evaluate.py`, la couverture s'est DÉGRADÉE (57 %
d'observations dans l'intervalle à 90 %, contre 63 % avec les lois Beta), parce que
normaliser une ligne à 1 couple ses cellules et borne le déplacement de chacune.
Le modèle n'invente plus de valeurs, mais il est plus trop-confiant qu'avant.

Usage :
    python scripts/analyses/diagnostics.py                    # complet
    python scripts/analyses/diagnostics.py --n-simus 200      # version rapide
    python scripts/analyses/diagnostics.py --only monte-carlo
"""

import argparse
import time

import pandas as pd

from analyse_legislatives import simulation
from analyse_legislatives.data import load_full_results
from analyse_legislatives.config import DEFAULT_N_SIMUS, DEFAULT_SEED
from analyse_legislatives.models import DEFAULT_MODEL, PUBLICATION_MODELS, build
from analyse_legislatives.projections import seats_by_simulation


def run_seats(
    districts,
    first_round_seats,
    seed: int,
    n_simus: int,
    model_name: str = DEFAULT_MODEL,
) -> pd.DataFrame:
    """Sièges par parti et par simulation (1er tour inclus) — exactement le même
    chemin de code que l'app (`models.build` + `simulation.run` +
    `projections.seats_by_simulation`)."""
    cube = simulation.run(build(model_name, seed=seed), districts, n_simus)
    return pd.DataFrame(seats_by_simulation(cube, first_round_seats).to_dicts())


def summarize(seats: pd.DataFrame) -> pd.DataFrame:
    """Médiane et intervalle à 90% par parti, plus la largeur de l'intervalle."""
    return pd.DataFrame(
        {
            "p05": seats.quantile(0.05).round(0).astype(int),
            "mediane": seats.median().round(0).astype(int),
            "p95": seats.quantile(0.95).round(0).astype(int),
            "largeur": (seats.quantile(0.95) - seats.quantile(0.05))
            .round(0)
            .astype(int),
        }
    )


def monte_carlo_error(districts, first_round_seats, seeds, n_simus) -> int:
    print("\n" + "=" * 72)
    print(
        f"1. ERREUR MONTE-CARLO — N = {n_simus}, {len(seeds)} seeds, modèle {DEFAULT_MODEL}"
    )
    print("=" * 72)

    per_seed = {
        seed: summarize(run_seats(districts, first_round_seats, seed, n_simus))
        for seed in seeds
    }

    spreads = {}
    for stat in ["p05", "mediane", "p95"]:
        table = pd.DataFrame({seed: s[stat] for seed, s in per_seed.items()})
        spread = table.max(axis=1) - table.min(axis=1)
        spreads[stat] = spread
        table["écart max"] = spread
        print(f"\n--- {stat} par seed ---")
        print(table.to_string())

    worst = int(pd.DataFrame(spreads).max().max())
    print(
        f"\nÉcart maximal entre seeds, toutes statistiques confondues : {worst} sièges."
    )
    print(
        "Lecture : cet écart est du bruit d'échantillonnage Monte-Carlo pur (même "
        "modèle, mêmes paramètres). Toute différence de cet ordre entre deux "
        "variantes du modèle n'est pas interprétable."
    )
    return worst


def compare_models(districts, first_round_seats, seed, n_simus, noise_floor=None):
    """Les trois variantes publiables, sur la même configuration et la même seed."""
    print("\n" + "=" * 72)
    print("2. COMPARAISON DES VARIANTES")
    print("=" * 72)

    summaries = {}
    for name in PUBLICATION_MODELS:
        t0 = time.time()
        seats = run_seats(districts, first_round_seats, seed, n_simus, name)
        summaries[name] = summarize(seats)
        print(f"\nmodèle = {name}   ({time.time() - t0:.0f}s)")
        print(summaries[name].to_string())

    medians = pd.DataFrame({n: s["mediane"] for n, s in summaries.items()})
    widths = pd.DataFrame({n: s["largeur"] for n, s in summaries.items()})

    print("\n--- Médiane (sièges) par variante ---")
    print(medians.to_string())
    print("\n--- Largeur de l'intervalle à 90% (sièges) par variante ---")
    print(widths.to_string())

    print(
        "\nLecture : les trois variantes partagent les mêmes ordres de préférence, "
        "donc la même loi nationale des taux de report. Les écarts ci-dessus ne "
        "viennent donc QUE de la structure de la variation locale."
    )
    if noise_floor is not None:
        spread = int((medians.max(axis=1) - medians.min(axis=1)).max())
        verdict = (
            "du même ordre que le bruit Monte-Carlo : non interprétable"
            if spread <= noise_floor
            else "au-delà du bruit Monte-Carlo : l'écart est réel"
        )
        print(
            f"\nÉcart maximal entre variantes sur les médianes : {spread} sièges "
            f"(bruit Monte-Carlo mesuré : {noise_floor}) — {verdict}."
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=DEFAULT_N_SIMUS)
    parser.add_argument("--seeds", type=int, nargs="+", default=[DEFAULT_SEED, 1, 2])
    parser.add_argument(
        "--only",
        choices=["monte-carlo", "models"],
        help="ne lancer qu'un seul des deux diagnostics",
    )
    args = parser.parse_args()

    first_round = load_full_results()
    districts, first_round_seats = first_round.districts, first_round.first_round_seats
    print(f"{len(districts)} circonscriptions simulées, N = {args.n_simus} tirages")

    noise_floor = None
    if args.only in (None, "monte-carlo"):
        noise_floor = monte_carlo_error(
            districts, first_round_seats, args.seeds, args.n_simus
        )
    if args.only in (None, "models"):
        compare_models(
            districts, first_round_seats, args.seeds[0], args.n_simus, noise_floor
        )


if __name__ == "__main__":
    main()
