"""Conditionne les intervalles de sièges sur les suffrages exprimés observés.

Cette analyse rétrospective rapproche, par identifiant de tirage, les sièges et
la part nationale de suffrages exprimés déjà stockés par ``evaluate.py``. Elle
conserve les tirages situés dans une fenêtre autour de la valeur réelle du
second tour ; elle ne relance donc aucune simulation.
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl

from analyse_legislatives.config import PROJECT_ROOT
from analyse_legislatives.models import PUBLICATION_MODELS
from analyse_legislatives.parties import SPECTRUM_LABELS

DEFAULT_INPUT_DIR = PROJECT_ROOT / "artifacts/publication/models"
DEFAULT_OUTPUT = DEFAULT_INPUT_DIR / "seat-intervals-conditioned-on-expressed.csv"
DEFAULT_WINDOW_POINTS = 0.5


def summarize_model(
    model: str,
    input_dir: Path,
    window_points: float,
) -> list[dict[str, float | int | str]]:
    seats = pl.read_csv(input_dir / f"joint-diagnostics-{model}.csv")
    expressed = (
        pl.read_csv(input_dir / f"expressed-diagnostics-{model}.csv")
        .filter(pl.col("scope") == "national_draw")
        .select("draw", "predicted_share", "actual_share")
    )
    observed = seats.filter(pl.col("role") == "observed")
    if observed.height != 1:
        raise ValueError(f"{model}: une unique ligne observée est attendue")

    draws = seats.filter(pl.col("draw") >= 0).join(
        expressed, on="draw", how="inner", validate="1:1"
    )
    if draws.height != expressed.height:
        raise ValueError(
            f"{model}: les tirages de sièges et de participation divergent"
        )
    target = float(expressed.get_column("actual_share").item(0))
    selected = draws.filter((pl.col("predicted_share") - target).abs() <= window_points)
    if selected.height < 100:
        raise ValueError(
            f"{model}: seulement {selected.height} tirages dans la fenêtre ; "
            "élargissez --window-points"
        )

    actual = observed.row(0, named=True)
    rows: list[dict[str, float | int | str]] = []
    for conditioning, sample in [
        ("Prior predictive", draws),
        ("Observed expressed share", selected),
    ]:
        for party in SPECTRUM_LABELS:
            values = sample.get_column(party).to_numpy()
            p05, p25, median, p75, p95 = np.quantile(
                values, [0.05, 0.25, 0.50, 0.75, 0.95]
            )
            rows.append(
                {
                    "model": model,
                    "conditioning": conditioning,
                    "party": party,
                    "actual": float(actual[party]),
                    "p05": float(p05),
                    "p25": float(p25),
                    "median": float(median),
                    "p75": float(p75),
                    "p95": float(p95),
                    "target_expressed_share": target,
                    "window_points": window_points,
                    "selected_draws": selected.height,
                    "total_draws": draws.height,
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--models", nargs="+", choices=PUBLICATION_MODELS, default=PUBLICATION_MODELS
    )
    parser.add_argument("--window-points", type=float, default=DEFAULT_WINDOW_POINTS)
    args = parser.parse_args()
    if args.window_points <= 0:
        parser.error("--window-points doit être strictement positif")

    rows = [
        row
        for model in args.models
        for row in summarize_model(model, args.input_dir, args.window_points)
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(args.output)
    print(f"wrote {args.output.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
