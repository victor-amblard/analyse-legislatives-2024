"""
Energy score des instituts de sondage, comparé à celui des modèles.

Le billet s'ouvre sur le constat que les fourchettes publiées ont manqué le RN.
Ce script transforme ce constat en score, sur la même métrique que le tableau des
métriques — mais il demande deux décisions explicites, sans lesquelles la
comparaison serait truquée.

1. LES SONDEURS NE PUBLIENT PAS DE LOI, seulement une fourchette. L'energy score
   exige un échantillon : on RECONSTRUIT donc une loi à partir de la fourchette.
   Deux lectures sont proposées — uniforme sur la fourchette, ou fourchette lue
   comme un intervalle à 90 % d'une gaussienne. Le classement ne bouge pas entre
   les deux, ce qui est la seule raison pour laquelle on peut s'en servir.

2. LES DÉCOUPAGES NE COÏNCIDENT PAS. Les sondeurs raisonnent en 5 blocs, le
   modèle en 7 familles, et les conventions divergent de 15 sièges sur ENS et de
   19 sur « Others » — pour des raisons de nomenclature, pas de qualité de
   prévision. Ces deux blocs sont donc ÉCARTÉS. Restent trois blocs où les deux
   conventions s'accordent à 3 sièges près, dont le RN, qui est justement celui
   dont parle l'introduction.

Chaque camp est noté contre la vérité de SA convention ; l'écart résiduel (1
siège sur le RN) est négligeable devant des scores de l'ordre de 20 à 50.
"""

import numpy as np
import polars as pl

from analyse_legislatives.config import DEFAULT_SEED, PROJECT_ROOT
from analyse_legislatives.evaluation import energy_score
from analyse_legislatives.models import PUBLICATION_MODELS
from analyse_legislatives.publication.sources import load_pollster_ranges

RESULTS_DIR = PROJECT_ROOT / "artifacts/publication/models"

BLOCKS = {
    "NFP + DVG": ["NFP+", "DVG"],
    "ENS and allies": ["ENS+"],
    "LR + DVD": ["LR", "DVD"],
    "RN and allies": ["RN+"],
    "Others": ["DIV"],
}

COMPARABLE = ["NFP + DVG", "LR + DVD", "RN and allies"]
"""Blocs dont les deux conventions s'accordent à 3 sièges près. ENS (15 sièges
d'écart) et Others (19) sont exclus : les y inclure noterait une différence de
nomenclature."""

N_DRAWS = 20000
POLLSTER_RANGES = load_pollster_ranges()
POLLSTERS = POLLSTER_RANGES.get_column("pollster").unique(maintain_order=True).to_list()
POLLSTER_RESULTS = dict(POLLSTER_RANGES.select("party", "actual").unique().iter_rows())


def pollster_samples(pollster: str, blocks, law: str, rng) -> np.ndarray:
    """Fourchette publiée -> échantillon. La loi est RECONSTRUITE, jamais publiée."""
    columns = []
    for block in blocks:
        row = POLLSTER_RANGES.filter(
            (pl.col("party") == block) & (pl.col("pollster") == pollster)
        ).row(0, named=True)
        low, high = row["low"], row["high"]
        if law == "uniform":
            columns.append(rng.uniform(low, high, N_DRAWS))
        else:
            columns.append(
                rng.normal((low + high) / 2, (high - low) / (2 * 1.645), N_DRAWS)
            )
    return np.column_stack(columns)


def model_samples(model: str, blocks):
    """Simulations du modèle, agrégées dans les blocs des sondeurs."""
    data = pl.read_csv(RESULTS_DIR / f"joint-diagnostics-{model}.csv")
    simulated = data.filter(pl.col("role") != "observed")
    observed = data.filter(pl.col("role") == "observed").row(0, named=True)
    samples = np.column_stack(
        [
            simulated.select(pl.sum_horizontal(BLOCKS[b])).to_numpy()[:, 0]
            for b in blocks
        ]
    )
    truth = [sum(int(observed[f]) for f in BLOCKS[b]) for b in blocks]
    return samples, truth


def main() -> None:
    truth_pollster = POLLSTER_RESULTS
    for law in ("uniform", "gaussian"):
        print(f"\n=== fourchette lue comme {law} ===")
        print(f"{'':22}{'RN seul (CRPS)':>16}{'3 blocs (ES)':>16}")
        scored = []
        for pollster in POLLSTERS:
            rng = np.random.default_rng(DEFAULT_SEED)
            rn = energy_score(
                pollster_samples(pollster, ["RN and allies"], law, rng),
                [truth_pollster["RN and allies"]],
            )
            rng = np.random.default_rng(DEFAULT_SEED)
            joint = energy_score(
                pollster_samples(pollster, COMPARABLE, law, rng),
                [truth_pollster[b] for b in COMPARABLE],
            )
            scored.append((pollster, rn, joint))
        for name, rn, joint in sorted(scored, key=lambda row: row[1]):
            print(f"  {name:20}{rn:>16.1f}{joint:>16.1f}")
        best = min(scored, key=lambda row: row[1])
        print(f"  meilleur institut : {best[0]}")

        print()
        for model in PUBLICATION_MODELS:
            rn_samples, rn_truth = model_samples(model, ["RN and allies"])
            joint_samples, joint_truth = model_samples(model, COMPARABLE)
            print(
                f"  {model:20}"
                f"{energy_score(rn_samples, rn_truth):>16.1f}"
                f"{energy_score(joint_samples, joint_truth):>16.1f}"
            )


if __name__ == "__main__":
    main()
