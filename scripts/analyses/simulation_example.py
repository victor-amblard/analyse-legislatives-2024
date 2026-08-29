"""Build the district example consumed by the animated simulation figure."""

import argparse
import json
from pathlib import Path

import numpy as np

from analyse_legislatives import simulation
from analyse_legislatives.config import DEFAULT_N_SIMUS, DEFAULT_SEED, PROJECT_ROOT
from analyse_legislatives.data import load_full_results, load_second_round_results
from analyse_legislatives.models import build
from analyse_legislatives.parties import DESTINATIONS, FAMILIES, NON_EXPRIMES
from analyse_legislatives.transfers import normalize_for_district

EXAMPLE_DISTRICT_ID = "0101"
EXAMPLE_MODEL = "national"
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts/publication/examples/district-0101.json"


def non_zero_rows(values) -> list[dict]:
    return [
        {"party": str(party), "value": int(value)}
        for party, value in values
        if value > 0
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=DEFAULT_N_SIMUS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    first_round = load_full_results()
    second_round = load_second_round_results()
    district = next(
        district
        for district in first_round.districts
        if district.circonscription.id == EXAMPLE_DISTRICT_ID
    )
    actual = second_round[EXAMPLE_DISTRICT_ID]

    competing = sorted(
        district.competing_parties_results.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    eliminated = sorted(
        district.eliminated_parties_results.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    source = next(party for party, votes in eliminated if votes > 0)
    focus_party = next(party for party, votes in competing if votes > 0)

    example_model = build(EXAMPLE_MODEL, seed=args.seed)
    parameters = example_model.draw_simulation()
    matrix = example_model.sample_transfer_matrices([district], parameters)[0]
    restricted = normalize_for_district(matrix, district, parameters.tilt)
    transfers = example_model.sample_transfers_in_circonscription(
        district, matrix, parameters.tilt
    )
    totals = {
        target: sum(row.get(target, 0) for row in transfers.values())
        for target in DESTINATIONS
    }

    predictive_model = build(EXAMPLE_MODEL, seed=args.seed)
    cube = simulation.run(predictive_model, [district], args.n_simus)
    focus_index = DESTINATIONS.index(focus_party)
    focus_votes = cube[:, 0, focus_index]
    winners = cube[:, 0, : len(FAMILIES)].argmax(axis=1)
    histogram_counts, histogram_edges = np.histogram(focus_votes, bins=14)

    actual_votes = sorted(actual.votes.items(), key=lambda item: item[1], reverse=True)
    artifact = {
        "schema_version": 1,
        "model": EXAMPLE_MODEL,
        "seed": args.seed,
        "n_simulations": args.n_simus,
        "national_district_count": len(first_round.districts),
        "sources": {
            "first_round": "data/processed/legislatives2024/data.csv",
            "second_round": "data/raw/legislatives2024/legislatives-2024-resultats-t2.csv",
            "model_config": "config/model.yaml",
        },
        "district": {
            "id": district.circonscription.id,
            "name": district.circonscription.name,
        },
        "first_round": {
            "competing": non_zero_rows(competing),
            "reservoirs": non_zero_rows(eliminated)
            + [{"party": NON_EXPRIMES, "value": district.non_expressed}],
        },
        "example_draw": {
            "source": str(source),
            "theta_row": [
                {"party": str(party), "value": float(value)}
                for party, value in sorted(
                    matrix.rates[source].items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ],
            "restricted_row": [
                {"party": str(party), "value": float(value)}
                for party, value in restricted.rates[source].items()
                if value > 0
            ],
            "multinomial": non_zero_rows(transfers[source].items()),
            "totals": non_zero_rows(
                sorted(
                    ((party, totals[party]) for party, votes in competing if votes > 0),
                    key=lambda item: item[1],
                    reverse=True,
                )
            ),
            "winner": str(
                max(
                    (party for party, votes in competing if votes > 0),
                    key=lambda party: totals[party],
                )
            ),
        },
        "predictive": {
            "focus_party": str(focus_party),
            "win_probability": float(np.mean(winners == focus_index)),
            "histogram_counts": histogram_counts.tolist(),
            "histogram_edges": histogram_edges.tolist(),
        },
        "actual": {
            "votes": non_zero_rows(actual_votes),
            "winner": actual_votes[0][0],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        displayed = args.output.relative_to(PROJECT_ROOT)
    except ValueError:
        displayed = args.output
    print(f"wrote {displayed}")


if __name__ == "__main__":
    main()
