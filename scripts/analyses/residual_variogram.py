"""
Le noyau décrit-il la BONNE structure de corrélation locale ?

Le modèle à noyau suppose que deux circonscriptions politiquement proches au 1er
tour s'écartent de la moyenne dans le même sens (hypothèse 6). Rien, avant le
scrutin, ne permet de valider cette similarité plutôt qu'une autre. Après le
scrutin, l'inférence écologique interdit toujours de reconstituer les taux de
report locaux — mais elle n'interdit pas de regarder les RÉSIDUS de quantités
observables, et de tester si leur structure spatiale ressemble à celle que le
modèle prédit.

C'est un variogramme. Pour un résidu standardisé `e_c = (observé - médiane) / sd`,
l'espérance du produit `e_c e_c'` est la corrélation entre les deux
circonscriptions. On range donc les paires par distance de Hellinger et l'on
compare, tranche par tranche :

  - `observé`  : moyenne des produits de résidus, sur l'unique réalisation ;
  - `modèle`   : corrélation entre les mêmes circonscriptions À TRAVERS les
                 tirages, c'est-à-dire ce que le modèle prédit vraiment (et non
                 le noyau latent, que les transformations non linéaires
                 atténuent).

Si la courbe observée est plate là où celle du modèle décroît, le noyau encode une
structure absente des données. Si elle décroît plus vite, la bande passante est
trop grande.

Un second test, indépendant du noyau, oppose une similarité concurrente : les
paires du MÊME département contre les autres. Si les résidus y sont bien plus
corrélés que le modèle ne le prévoit, c'est que la proximité géographique porte de
l'information que la composition du 1er tour ne capture pas.

ATTENTION : ce diagnostic utilise les résultats du second tour. C'est une analyse
*a posteriori*, au même titre que le conditionnement sur la participation — pas
une justification ex ante du noyau.

Usage :
    python scripts/analyses/residual_variogram.py
    python scripts/analyses/residual_variogram.py --quantity RN+ --n-simus 500
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl

from analyse_legislatives import simulation
from analyse_legislatives.config import DEFAULT_N_SIMUS, DEFAULT_SEED, PROJECT_ROOT
from analyse_legislatives.data import load_full_results, load_second_round_results
from analyse_legislatives.models import build
from analyse_legislatives.models.kernel import department_group
from analyse_legislatives.parties import FAMILIES
from analyse_legislatives.utils.progress import progress_bar
from first_round_variogram import hellinger_distances

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "publication" / "sensitivity"
FAMILY_LABELS = [str(family) for family in FAMILIES]
N_BINS = 8
MIN_SD = 1e-9
"""En deçà, la quantité simulée est constante : le résidu standardisé n'a pas de
sens et la circonscription est écartée plutôt que de produire un infini."""


def observed_and_simulated(quantity, cube, inscrits, votes_true, exprimes_true):
    """Renvoie (simulations, observé, masque des circonscriptions retenues).

    `exprimes` : part des suffrages exprimés parmi les inscrits, définie partout.
    Une famille politique : son score en % des exprimés, restreint aux
    circonscriptions où elle était qualifiée.
    """
    party_cube = cube[:, :, : len(FAMILIES)]
    exprimes_sim = party_cube.sum(axis=2)

    if quantity == "exprimes":
        sim = exprimes_sim / inscrits * 100
        obs = exprimes_true / inscrits * 100
        return sim, obs, np.ones(sim.shape[1], dtype=bool)

    k = FAMILY_LABELS.index(quantity)
    sim = np.where(
        exprimes_sim > 0, party_cube[:, :, k] / np.maximum(exprimes_sim, 1) * 100, 0.0
    )
    obs = votes_true[:, k] / exprimes_true * 100
    return sim, obs, votes_true[:, k] > 0


def variogram(sim, obs, distances, departements, n_bins=N_BINS):
    """Corrélation des résidus par tranche de distance, observée et prédite."""
    median = np.median(sim, axis=0)
    sd = sim.std(axis=0)
    keep = sd > MIN_SD
    sim, obs, sd, median = sim[:, keep], obs[keep], sd[keep], median[keep]
    distances = distances[np.ix_(keep, keep)]
    departements = np.asarray(departements)[keep]

    # Résidus standardisés, puis CENTRÉS sur leur moyenne entre circonscriptions.
    #
    # Sans ce centrage, `E[e_c e_c']` vaut `b^2 + rho` où `b` est le biais commun
    # du modèle : un biais national suffit à produire des « corrélations »
    # supérieures à 1, ce qui n'a aucun sens. Or avec UNE seule élection, un
    # écart commun à toutes les circonscriptions et un biais de la médiane sont
    # la même observation : la composante commune de la corrélation n'est pas
    # identifiable. Ce diagnostic ne peut donc tester que la FORME de la
    # dépendance — sa décroissance avec la distance — et non son niveau.
    #
    # Le centrage est appliqué des deux côtés, tirage par tirage pour le modèle,
    # afin que les deux colonnes mesurent la même chose.
    residual = (obs - median) / sd
    residual = residual - residual.mean()
    residual = residual / residual.std()
    observed_products = np.outer(residual, residual)

    simulated = (sim - median) / sd
    simulated = simulated - simulated.mean(axis=1, keepdims=True)
    model_corr = np.corrcoef(simulated.T)

    iu = np.triu_indices(len(residual), k=1)
    d, obs_p, mod_p = distances[iu], observed_products[iu], model_corr[iu]
    same_dept = (departements[:, None] == departements[None, :])[iu]

    edges = np.quantile(d, np.linspace(0, 1, n_bins + 1))
    edges[-1] += 1e-9
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (d >= lo) & (d < hi)
        if not m.any():
            continue
        rows.append(
            {
                "distance_min": float(lo),
                "distance_max": float(hi),
                "distance_moyenne": float(d[m].mean()),
                "paires": int(m.sum()),
                "correlation_modele": float(mod_p[m].mean()),
                "correlation_observee": float(obs_p[m].mean()),
            }
        )

    dept = {
        "meme_departement": {
            "paires": int(same_dept.sum()),
            "modele": float(mod_p[same_dept].mean()),
            "observe": float(obs_p[same_dept].mean()),
        },
        "departements_differents": {
            "paires": int((~same_dept).sum()),
            "modele": float(mod_p[~same_dept].mean()),
            "observe": float(obs_p[~same_dept].mean()),
        },
    }
    return rows, dept, int(keep.sum())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=DEFAULT_N_SIMUS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--model", default="kernel_anchored")
    parser.add_argument(
        "--quantity",
        nargs="+",
        default=["exprimes", "RN+", "ENS+", "NFP+"],
        help="'exprimes' ou une famille politique",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    first_round = load_full_results()
    actual = load_second_round_results()
    districts = [d for d in first_round.districts if d.circonscription.id in actual]
    ids = [d.circonscription.id for d in districts]
    inscrits = np.array([first_round.inscrits_by_id[i] for i in ids], dtype=float)
    votes_true = np.array(
        [[actual[i].votes.get(f, 0) for f in FAMILY_LABELS] for i in ids], dtype=float
    )
    exprimes_true = np.array([actual[i].exprimes for i in ids], dtype=float)
    departements = [department_group(i) for i in ids]

    model = build(args.model, seed=args.seed)
    with progress_bar(args.n_simus, args.model) as tick:
        cube = simulation.run(model, districts, args.n_simus, progress=tick)

    # Hellinger reste ici une distance descriptive du premier tour, pas un noyau.
    hellinger = hellinger_distances(districts)

    rows = []
    for quantity in args.quantity:
        sim, obs, mask = observed_and_simulated(
            quantity, cube, inscrits, votes_true, exprimes_true
        )
        sub = np.ix_(mask, mask)
        bins, dept, n_kept = variogram(
            sim[:, mask],
            obs[mask],
            hellinger[sub],
            [d for d, m in zip(departements, mask) if m],
        )

        print("\n" + "=" * 78)
        print(f"{quantity}  —  {n_kept} circonscriptions")
        print("=" * 78)
        print(f"  {'distance H':>14s} {'paires':>9s} {'modèle':>9s} {'observé':>9s}")
        for b in bins:
            print(
                f"  {b['distance_min']:.3f}–{b['distance_max']:.3f} {b['paires']:9d}"
                f" {b['correlation_modele']:9.3f} {b['correlation_observee']:9.3f}"
            )
            rows.append({"quantite": quantity, **b})

        print("\n  Test concurrent — proximité géographique")
        for label, d in dept.items():
            print(
                f"    {label:<26s} {d['paires']:8d} paires |"
                f" modèle {d['modele']:+.3f} | observé {d['observe']:+.3f}"
            )
            rows.append({"quantite": quantity, "groupe": label, **d})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / "residual-variogram.csv"
    pl.DataFrame(rows, infer_schema_length=None).write_csv(path)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
