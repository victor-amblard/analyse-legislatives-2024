"""
Modèle de référence : « le qualifié arrivé en tête au premier tour gagne ».

Répond à la question « combien obtient-on sans rien modéliser du tout ? ». La
règle n'utilise ni report, ni désistement, ni participation : elle recopie
l'ordre du premier tour parmi les candidats encore en lice. Tout ce que les
modèles gagnent sur elle est donc, littéralement, ce que les reports apportent.

La prévision étant déterministe, son energy score se réduit à la distance
euclidienne de son vecteur de sièges au résultat réel — la même unité, en
sièges, que la colonne « ES national » du billet. Elle se lit donc directement en
face des modèles, dont on recalcule ici l'energy score à partir des tirages déjà
écrits par `scripts/evaluate.py`.

Usage :
    python scripts/analyses/first_round_leader.py
    python scripts/analyses/first_round_leader.py --csv out.csv
    python scripts/analyses/first_round_leader.py --results-dir artifacts/essai
"""

import argparse
import re
from pathlib import Path

import numpy as np
import polars as pl

from analyse_legislatives.baselines import (
    NO_WINNER,
    first_round_leader_seats,
    first_round_leader_winners,
)
from analyse_legislatives.config import PROJECT_ROOT
from analyse_legislatives.evaluation import energy_score
from analyse_legislatives.data import load_full_results, load_second_round_results
from analyse_legislatives.models import PUBLICATION_MODELS
from analyse_legislatives.parties import FAMILIES, SPECTRUM_LABELS

RESULTS_DIR = PROJECT_ROOT / "artifacts/publication/models"
DEFAULT_CSV = RESULTS_DIR / "baseline-first-round-leader.csv"

FAMILY_LABELS = [str(family) for family in FAMILIES]

WINNER_LINE = re.compile(r"Vainqueur : ([\d.]+)% de circonscriptions correctes")


def model_scores(model: str, results_dir: Path) -> tuple[float, float] | None:
    """Energy score et distance du scénario médian, depuis les tirages écrits.

    Recalculés plutôt que relus dans le rapport texte : c'est le même estimateur
    que celui appliqué à la référence, donc la comparaison ne dépend d'aucune
    mise en forme.
    """
    path = results_dir / f"joint-diagnostics-{model}.csv"
    if not path.exists():
        return None
    data = pl.read_csv(path)
    samples = data.filter(pl.col("role") != "observed").select(FAMILY_LABELS).to_numpy()
    truth = (
        data.filter(pl.col("role") == "observed").select(FAMILY_LABELS).to_numpy()[0]
    )
    median_distance = float(np.linalg.norm(np.median(samples, axis=0) - truth))
    return energy_score(samples, truth), median_distance


def model_accuracy(model: str, results_dir: Path) -> float | None:
    """Part de circonscriptions au bon vainqueur, lue dans le rapport d'évaluation.

    Elle demanderait sinon de relancer les simulations : c'est la seule métrique
    de ce script qui ne se reconstruit pas depuis les tirages sauvegardés.
    """
    path = results_dir / f"evaluation-{model}.txt"
    if not path.exists():
        return None
    match = WINNER_LINE.search(path.read_text(encoding="utf-8"))
    return float(match.group(1)) / 100 if match else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help="détail des sièges par famille politique",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=RESULTS_DIR,
        help="artefacts des modèles auxquels comparer la référence",
    )
    args = parser.parse_args()

    first_round = load_full_results()
    actual = load_second_round_results()
    districts = [d for d in first_round.districts if d.circonscription.id in actual]

    predicted = first_round_leader_winners(districts)
    undecided = int(np.count_nonzero(predicted == NO_WINNER))
    if undecided:
        raise ValueError(
            f"{undecided} circonscriptions sans candidat qualifié : la règle de "
            "référence n'y désigne personne."
        )

    votes_true = np.array(
        [
            [actual[d.circonscription.id].votes.get(f, 0) for f in FAMILY_LABELS]
            for d in districts
        ],
        dtype=float,
    )
    winners_true = votes_true.argmax(axis=1)

    seats = first_round_leader_seats(districts, first_round.first_round_seats)
    seats_true = np.array(
        [np.count_nonzero(winners_true == k) for k in range(len(FAMILIES))],
        dtype=float,
    ) + np.array(
        [first_round.first_round_seats.get(f, 0) for f in FAMILY_LABELS], dtype=float
    )

    accuracy = float((predicted == winners_true).mean())
    distance = float(np.linalg.norm(seats - seats_true))

    print(
        f"{len(districts)} circonscriptions évaluées | modèle de référence "
        f"« tête au 1er tour » (déterministe)"
    )
    print("\n" + "=" * 74)
    print("NIVEAU NATIONAL")
    print("=" * 74)
    print(f"\n  {'parti':>6s} {'réel':>6s} {'référence':>11s} {'écart':>8s}")
    for family in SPECTRUM_LABELS:
        k = FAMILY_LABELS.index(family)
        print(
            f"  {family:>6s} {seats_true[k]:6.0f} {seats[k]:11.0f} "
            f"{seats[k] - seats_true[k]:+8.0f}"
        )

    # Une prévision déterministe est une masse de Dirac : son terme de dispersion
    # est nul, donc son energy score EST la distance à la vérité. C'est ce qui
    # autorise à l'aligner avec la colonne « ES national » des modèles.
    print(f"\n  Energy score (= distance au résultat réel) : {distance:8.2f} sièges")
    print(
        "      aucune incertitude déclarée : la référence ne peut ni couvrir "
        "ni manquer un intervalle."
    )

    print("\n" + "=" * 74)
    print("PAR CIRCONSCRIPTION")
    print("=" * 74)
    print(
        f"\n  Vainqueur : {accuracy:.1%} de circonscriptions correctes "
        f"({(predicted == winners_true).sum()}/{len(districts)})"
    )

    print("\n" + "=" * 74)
    print("COMPARAISON AUX MODÈLES")
    print("=" * 74)
    print(f"\n  {'modèle':>20s} {'ES':>8s} {'scénario médian':>17s} {'vainqueur':>11s}")
    print(
        f"  {'référence 1er tour':>20s} {distance:8.2f} {distance:17.2f} {accuracy:11.1%}"
    )
    for model in PUBLICATION_MODELS:
        scores = model_scores(model, args.results_dir)
        if scores is None:
            print(f"  {model:>20s} {'—':>8s} {'—':>17s} {'—':>11s}  (artefact absent)")
            continue
        es, median_distance = scores
        model_hits = model_accuracy(model, args.results_dir)
        hits = f"{model_hits:11.1%}" if model_hits is not None else f"{'—':>11s}"
        print(f"  {model:>20s} {es:8.2f} {median_distance:17.2f} {hits}")
    print(
        "\n  Les modèles ne battent la référence que s'ils font mieux que ces "
        "deux colonnes ;\n  leur valeur ajoutée propre est l'incertitude, que la "
        "référence ne fournit pas."
    )

    rows = [
        {
            "party": family,
            "baseline_seats": seats[FAMILY_LABELS.index(family)],
            "actual_seats": seats_true[FAMILY_LABELS.index(family)],
            "error": seats[FAMILY_LABELS.index(family)]
            - seats_true[FAMILY_LABELS.index(family)],
        }
        for family in SPECTRUM_LABELS
    ]
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(args.csv)
    print(f"\nSièges de la référence écrits dans {args.csv}")


if __name__ == "__main__":
    main()
