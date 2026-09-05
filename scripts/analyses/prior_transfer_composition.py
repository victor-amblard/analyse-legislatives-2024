"""
Ce que l'ordre de préférence déclaré implique, concrètement, dans un duel.

Le billet déclare un ORDRE et rien d'autre. Le lecteur est en droit de demander
d'où sortent alors des taux de report. Ce script répond avec la seule chose
honnête : la loi a priori des lignes de report, restreinte aux candidats
réellement en lice et renormalisée — c'est-à-dire la ligne qui agit vraiment.

AUCUN résultat du second tour n'intervient. La figure produite est la version
*a priori* de celle de `research/compare_retrospective.py`, dont elle réutilise
le tracé : les deux se lisent donc côte à côte, l'une montrant ce que le modèle
croit avant le scrutin et l'autre ce que l'inférence écologique en dit après.

DEUX PIÈGES ÉVITÉS ICI :

1. La ligne NON restreinte n'a aucun sens. Sur six destinations dont quatre ne
   sont pas sur le bulletin, le report vers la moins préférée paraît minuscule
   par pure mécanique ; après restriction au duel et renormalisation, il ne l'est
   plus du tout. Seule la ligne restreinte est appliquée, donc seule elle mérite
   d'être publiée.

2. Une circonscription n'est pas le bloc. Les taux sont agrégés nationalement en
   PONDÉRANT PAR LES VOIX du réservoir, exactement comme le fait l'analyse
   rétrospective — sans quoi on comparerait une circonscription à une moyenne.

Usage :
    python scripts/analyses/prior_transfer_composition.py
    python scripts/analyses/prior_transfer_composition.py --duels "NFP+,RN+" --n-simus 500
"""

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.compare_retrospective import chart  # noqa: E402

from analyse_legislatives.config import (  # noqa: E402
    DEFAULT_N_SIMUS,
    DEFAULT_SEED,
    PROJECT_ROOT,
)
from analyse_legislatives.data import load_full_results  # noqa: E402
from analyse_legislatives.models import build  # noqa: E402
from analyse_legislatives.parties import (  # noqa: E402
    FAMILIES,
    NON_EXPRIMES,
    PoliticalFamily,
)
from analyse_legislatives.transfers import normalize_for_district  # noqa: E402
from analyse_legislatives.utils.progress import progress_bar  # noqa: E402

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "publication" / "prior"
DEFAULT_FIGURE_DIR = PROJECT_ROOT / "site" / "public" / "figures"
DEFAULT_DUELS = ("NFP+,RN+", "ENS+,RN+")
MIN_RESERVOIR_SHARE = 0.03
"""Un réservoir pesant moins de 3 % des voix éliminées du bloc n'est pas tracé :
il ajouterait une ligne de bruit à une figure qui doit rester lisible."""


def districts_of(duel: tuple[PoliticalFamily, ...], first_round):
    """Circonscriptions dont l'ensemble des qualifiés est EXACTEMENT ce duel."""
    wanted = set(duel)
    return [
        d
        for d in first_round.districts
        if {p for p in FAMILIES if d.competing_parties_results.get(p, 0) > 0} == wanted
    ]


def reservoirs(districts, duel) -> dict[PoliticalFamily, np.ndarray]:
    """Voix éliminées par famille source, une entrée par circonscription."""
    pools = {}
    for source in FAMILIES:
        if source in duel:
            continue
        votes = np.array(
            [d.eliminated_parties_results.get(source, 0) for d in districts],
            dtype=float,
        )
        if votes.sum() > 0:
            pools[source] = votes
    total = sum(v.sum() for v in pools.values())
    return {
        source: votes
        for source, votes in pools.items()
        if votes.sum() >= MIN_RESERVOIR_SHARE * total
    }


def draw_rates(model, districts, pools, duel, n_simus, label):
    """Un tirage = une ligne de report nationale par source, pondérée par les voix.

    Le tirage des paramètres globaux est fait UNE fois par simulation et partagé
    par toutes les circonscriptions du bloc : c'est ce qui donne son sens à la
    moyenne nationale, les écarts locaux se compensant à l'intérieur.
    """
    destinations = [*duel, NON_EXPRIMES]
    rows = []
    with progress_bar(n_simus, label) as tick:
        for index in range(n_simus):
            draw = model.draw_simulation()
            matrices = model.sample_transfer_matrices(districts, draw)
            tilts = model.tilts_for_districts(districts, draw)
            restricted = [
                normalize_for_district(matrix, district, float(tilt))
                for matrix, district, tilt in zip(matrices, districts, tilts)
            ]
            for source, votes in pools.items():
                rates = np.array(
                    [
                        [r.rates[source].get(target, 0.0) for target in destinations]
                        for r in restricted
                    ]
                )
                national = votes @ rates / votes.sum()
                for target, value in zip(destinations, national):
                    rows.append(
                        {
                            "model": "prior",
                            "duel": "/".join(str(p) for p in duel),
                            "chain": 0,
                            "draw": index,
                            "source": str(source),
                            "destination": str(target),
                            "rate": float(value),
                        }
                    )
            tick(index + 1)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=DEFAULT_N_SIMUS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--model", default="national")
    parser.add_argument("--duels", nargs="+", default=list(DEFAULT_DUELS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--figure-dir", type=Path, default=DEFAULT_FIGURE_DIR)
    args = parser.parse_args()

    first_round = load_full_results()
    rows = []
    for spec in args.duels:
        duel = tuple(PoliticalFamily(part.strip()) for part in spec.split(","))
        districts = districts_of(duel, first_round)
        if not districts:
            raise ValueError(f"Aucune circonscription pour le duel {spec}.")
        pools = reservoirs(districts, duel)
        print(
            f"\n{'/'.join(map(str, duel))} : {len(districts)} circonscriptions, "
            f"réservoirs retenus {', '.join(str(s) for s in pools)}"
        )
        model = build(args.model, seed=args.seed)
        rows.extend(
            draw_rates(
                model,
                districts,
                pools,
                duel,
                args.n_simus,
                "/".join(str(p) for p in duel),
            )
        )

    draws = pl.DataFrame(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    draws_path = args.output_dir / "prior-transfer-draws.csv"
    draws.write_csv(draws_path)

    summary = (
        draws.group_by(["duel", "source", "destination"])
        .agg(
            pl.col("rate").quantile(0.05).alias("q05"),
            pl.col("rate").median().alias("mediane"),
            pl.col("rate").quantile(0.95).alias("q95"),
        )
        .sort("duel", "source", "destination")
    )
    summary_path = args.output_dir / "prior-transfer-composition.csv"
    summary.write_csv(summary_path)

    print("\nLignes de report a priori, restreintes et pondérées par les voix :")
    for row in summary.iter_rows(named=True):
        print(
            f"  {row['duel']:<12} {row['source']:<5} -> {row['destination']:<14}"
            f" médiane {100 * row['mediane']:5.1f} %"
            f"  IC90 [{100 * row['q05']:4.1f} ; {100 * row['q95']:4.1f}]"
        )

    # Hétérogène (str et dict) : sans annotation, l'inférence en fait un
    # `dict[str, Collection[str]]` que `**` ne peut plus rapprocher des
    # paramètres de `chart`.
    chart_options: dict[str, Any] = {
        "models": ["prior"],
        "display_labels": {NON_EXPRIMES: "Non exprimés"},
        "axis_title": "Part des électeurs du 1er tour",
        "tooltip_titles": {
            "source": "Réservoir du 1er tour",
            "destination": "Destination",
            "interval": "Médiane [intervalle à 90 %]",
        },
        "title": "Ce que l'ordre de préférence déclaré implique",
        "subtitle": (
            "Distribution a priori des reports, restreinte aux candidats en lice — "
            "aucun résultat du second tour n'intervient"
        ),
    }
    args.figure_dir.mkdir(parents=True, exist_ok=True)
    figure_path = args.figure_dir / "prior-transfer-composition.svg"
    chart(draws, **chart_options).save(figure_path)
    dark_figure_path = args.figure_dir / "prior-transfer-composition-dark.svg"
    chart(draws, dark=True, **chart_options).save(dark_figure_path)

    print(f"\nwrote {draws_path}")
    print(f"wrote {summary_path}")
    print(f"wrote {figure_path}")
    print(f"wrote {dark_figure_path}")


if __name__ == "__main__":
    main()
