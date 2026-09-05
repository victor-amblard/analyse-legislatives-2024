"""Animate the prior predictive distribution for district 0101."""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
import numpy as np

from analyse_legislatives import simulation
from analyse_legislatives.config import DEFAULT_SEED, PROJECT_ROOT
from analyse_legislatives.data import load_full_results
from analyse_legislatives.models import build
from analyse_legislatives.parties import DESTINATIONS, NON_EXPRIMES, PoliticalFamily
from analyse_legislatives.viz.palette import POLITICAL_FAMILY_COLORS

DISTRICT_ID = "0101"
DEFAULT_N_SIMULATIONS = 20_000
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "site/public/figures"


def _axis_limits(values: np.ndarray) -> tuple[float, float]:
    low, high = np.quantile(values, [0.001, 0.999])
    padding = max((high - low) * 0.08, 0.01)
    return max(0.0, low - padding), min(1.0, high + padding)


def _frame_counts(n: int, count: int = 42) -> np.ndarray:
    """More frames at the start, when the running probability moves most."""
    return np.unique(np.geomspace(8, n, count).astype(int))


def _draw(
    shares: np.ndarray,
    *,
    output: Path,
    dark: bool,
) -> None:
    lr = shares[:, 0]
    rn = shares[:, 1]
    non_expressed = shares[:, 2]
    lr_wins = lr > rn
    counts = _frame_counts(len(shares))

    background = "#14161a" if dark else "#fbfbfc"
    foreground = "#e9eaee" if dark else "#16181d"
    muted = "#aeb4c0" if dark else "#68707d"
    grid = "#343944" if dark else "#e3e5ea"
    lr_colour = POLITICAL_FAMILY_COLORS[PoliticalFamily.LR]
    rn_colour = POLITICAL_FAMILY_COLORS[PoliticalFamily.RNx]

    fig, ax = plt.subplots(figsize=(6.6, 4.4), dpi=100)
    fig.patch.set_facecolor(background)
    ax.set_facecolor(background)
    xlim, ylim = _axis_limits(lr), _axis_limits(rn)
    ax.set(xlim=xlim, ylim=ylim)
    ax.set_xlabel("LR (% des inscrits)", color=foreground)
    ax.set_ylabel("RN+ (% des inscrits)", color=foreground)
    ax.set_title(
        "0101 : la distribution prédictive se dessine",
        loc="left",
        color=foreground,
        fontsize=13,
        fontweight="bold",
        pad=28,
    )
    ax.grid(color=grid, linewidth=0.7)
    ax.tick_params(colors=muted)
    ax.xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    ax.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    for spine in ax.spines.values():
        spine.set_color(grid)

    diagonal_low = max(xlim[0], ylim[0])
    diagonal_high = min(xlim[1], ylim[1])
    ax.plot(
        [diagonal_low, diagonal_high],
        [diagonal_low, diagonal_high],
        color=muted,
        linewidth=1,
        linestyle="--",
    )
    ax.text(
        diagonal_high,
        diagonal_high,
        "égalité",
        color=muted,
        fontsize=8,
        ha="right",
        va="bottom",
    )

    # Since LR + RN+ + non-expressed = 100%, these diagonals expose the third
    # coordinate without turning the chart into a ternary diagram.
    for level in (0.2, 0.3, 0.4, 0.5):
        xs = np.array(xlim)
        ys = 1 - level - xs
        visible = (ys >= ylim[0]) & (ys <= ylim[1])
        if visible.any():
            ax.plot(xs[visible], ys[visible], color=grid, linewidth=0.8)
            index = np.flatnonzero(visible)[-1]
            at_left_edge = xs[index] <= xlim[0] + 0.002
            ax.text(
                xs[index] + (0.002 if at_left_edge else -0.002),
                ys[index],
                f"non-exprimés {level:.0%}",
                color=muted,
                fontsize=7,
                ha="left" if at_left_edge else "right",
                va="bottom",
            )

    points = ax.scatter([], [], s=7, alpha=0.28, linewidths=0, rasterized=True)
    status = ax.text(
        0,
        1.015,
        "",
        transform=ax.transAxes,
        color=foreground,
        fontsize=10,
        va="bottom",
    )
    legend = ax.legend(
        handles=[
            plt.Line2D(
                [], [], marker="o", linestyle="", color=lr_colour, label="LR gagne"
            ),
            plt.Line2D(
                [], [], marker="o", linestyle="", color=rn_colour, label="RN+ gagne"
            ),
        ],
        loc="lower right",
        frameon=False,
        fontsize=8,
    )
    for text in legend.get_texts():
        text.set_color(foreground)

    def update(frame: int):
        n = int(counts[frame])
        points.set_offsets(np.column_stack((lr[:n], rn[:n])))
        points.set_color(np.where(lr_wins[:n], lr_colour, rn_colour).tolist())
        probability = lr_wins[:n].mean()
        median_non_expressed = np.median(non_expressed[:n])
        status.set_text(
            f"{n:,} simulations  ·  victoire de LR : {probability:.0%}  ·  "
            f"non-exprimés médians : {median_non_expressed:.1%}"
        )
        return points, status

    animation = FuncAnimation(
        fig,
        update,
        frames=len(counts),
        interval=110,
        blit=False,
        repeat=True,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    animation.save(output, writer=PillowWriter(fps=7), dpi=100)
    update(len(counts) - 1)
    fig.savefig(output.with_suffix(".png"), dpi=120, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=DEFAULT_N_SIMULATIONS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--theme", choices=("light", "dark", "both"), default="both")
    args = parser.parse_args()

    first_round = load_full_results()
    district = next(
        district
        for district in first_round.districts
        if district.circonscription.id == DISTRICT_ID
    )
    cube = simulation.run(build("national", seed=args.seed), [district], args.n_simus)
    indices = [
        DESTINATIONS.index(PoliticalFamily.LR),
        DESTINATIONS.index(PoliticalFamily.RNx),
        DESTINATIONS.index(NON_EXPRIMES),
    ]
    selected = cube[:, 0, indices].astype(float)
    shares = selected / selected.sum(axis=1, keepdims=True)

    themes = {
        "light": (("", False),),
        "dark": (("-dark", True),),
        "both": (("", False), ("-dark", True)),
    }
    for suffix, dark in themes[args.theme]:
        output = args.output_dir / f"district-0101-simulations{suffix}.gif"
        _draw(shares, output=output, dark=dark)
        try:
            displayed = output.relative_to(PROJECT_ROOT)
        except ValueError:
            displayed = output
        print(f"wrote {displayed}")


if __name__ == "__main__":
    main()
