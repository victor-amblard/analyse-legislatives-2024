from collections.abc import Mapping, Sequence
import numpy as np
import polars as pl

from analyse_legislatives.circonscription import CirconscriptionResult
from analyse_legislatives.data import district_ids
from analyse_legislatives.parties import (
    DESTINATIONS,
    FAMILIES,
    NON_EXPRIMES,
    SPECTRUM_LABELS,
)

ABS_INDEX = DESTINATIONS.index(NON_EXPRIMES)
PARTY_SLICE = slice(0, len(FAMILIES))


def district_summary(
    simulation_results: np.ndarray, district_index: int, confidence_width=0.1
) -> pl.DataFrame:
    """
    Prend en entrée le résultat des simulations (n_simus, n_districts, n_parties)
    """
    votes = simulation_results[:, district_index, PARTY_SLICE]
    winners = votes.argmax(axis=1)
    return (
        pl.DataFrame(
            {
                "parti": [str(f) for f in FAMILIES],
                "moyenne": votes.mean(axis=0),
                "p05": np.quantile(votes, confidence_width / 2, axis=0),
                "mediane": np.median(votes, axis=0),
                "p95": np.quantile(votes, 1 - confidence_width / 2, axis=0),
                "% de victoires": [
                    (winners == k).mean() * 100 for k in range(len(FAMILIES))
                ],
                "en_lice": votes.max(axis=0) > 0,
            }
        )
        .filter("en_lice")
        .drop("en_lice")
        .sort("mediane", descending=True)
    )


def closest_to_marginal_median(seats_by_simu: pl.DataFrame) -> dict[str, float]:
    """Renvoie le tirage réel le plus proche des médianes marginales."""
    values = seats_by_simu.to_numpy()
    median = np.median(values, axis=0)
    index = int(np.square(values - median).sum(axis=1).argmin())
    return seats_by_simu.row(index, named=True)


def median_scenario_seats(seats_by_simu: pl.DataFrame) -> dict[str, float]:
    """Scénario national simulé le plus proche des médianes marginales."""
    return closest_to_marginal_median(seats_by_simu)


def median_scenario_district(
    district_frame: pl.DataFrame, party_a: str, party_b: str
) -> dict[str, float]:
    """Scénario représentatif d'un duel, non-exprimés inclus."""
    wide = (
        district_frame.filter(pl.col("party").is_in([party_a, party_b, NON_EXPRIMES]))
        .pivot(on="party", index="id_simu", values="votes")
        .drop("id_simu")
        .select([party_a, party_b, NON_EXPRIMES])
    )
    return closest_to_marginal_median(wide)


def winners_by_simulation(simulation_results: np.ndarray) -> np.ndarray:
    """Indice du vainqueur de chaque circonscription, hors non-exprimés."""
    return simulation_results[:, :, PARTY_SLICE].argmax(axis=2)


def add_first_round_seats(
    seats_by_simu: pl.DataFrame, first_round_seats: Mapping[str, int]
) -> pl.DataFrame:
    """Ajoute les sièges acquis au premier tour et impose l'ordre politique."""
    expressions = []
    for party in SPECTRUM_LABELS:
        base = pl.col(party) if party in seats_by_simu.columns else pl.lit(0)
        expressions.append((base + first_round_seats.get(party, 0)).alias(party))
    return seats_by_simu.select(expressions)


def seats_by_simulation(
    cube: np.ndarray, first_round_seats: Mapping[str, int]
) -> pl.DataFrame:
    """Une ligne par simulation, une colonne de sièges par famille politique."""
    winners = winners_by_simulation(cube)
    counts = np.stack(
        [(winners == k).sum(axis=1) for k in range(len(FAMILIES))], axis=1
    )
    seats = pl.DataFrame(counts, schema=[str(f) for f in FAMILIES], orient="row")
    return add_first_round_seats(seats, first_round_seats)


def expressed_share_by_simulation(
    cube: np.ndarray,
    districts: Sequence[CirconscriptionResult],
    inscrits_by_id: Mapping[str, int],
) -> pl.Series:
    """Part nationale simulée de suffrages exprimés parmi les inscrits."""
    total_inscrits = sum(inscrits_by_id[i] for i in district_ids(districts))
    non_expressed = cube[:, :, ABS_INDEX].sum(axis=1)
    return pl.Series("expressed_share", 100 - non_expressed / total_inscrits * 100)


def conditional_seats_by_non_expressed(
    seats_by_simu: pl.DataFrame, expressed_share: pl.Series, confidence_width=0.1
) -> pl.DataFrame:
    """Résume les sièges par tranche d'un point de non-expression."""
    if seats_by_simu.height != len(expressed_share):
        raise ValueError(
            "Les sièges et le taux exprimé doivent avoir une ligne par simulation."
        )

    return (
        seats_by_simu.with_columns((100 - expressed_share).alias("non_exprimés"))
        .unpivot(index="non_exprimés", variable_name="parti", value_name="sièges")
        .with_columns(
            pl.col("non_exprimés").floor().cast(pl.Int64).alias("tranche_basse")
        )
        .group_by(["parti", "tranche_basse"])
        .agg(
            pl.col("sièges").median().alias("sieges_medians"),
            pl.len().alias("simulations"),
            pl.col("sièges").quantile(confidence_width / 2).alias("p05"),
            pl.col("sièges").quantile(1 - confidence_width / 2).alias("p95"),
        )
        .with_columns(
            (pl.col("tranche_basse") + 1).alias("tranche_haute"),
            (pl.col("tranche_basse") + 0.5).alias("non_exprimés"),
        )
        .sort(["parti", "tranche_basse"])
    )


def conditional_wins_by_non_expressed(
    simulation_results: np.ndarray,
    district_index: int,
    inscrits: int,
    min_draws: int = 30,
) -> pl.DataFrame:
    """
    Probabilité de victoire de chaque parti par tranche d'un point de
    non-exprimés, dans UNE circonscription.

    Pendant local de `conditional_seats_by_non_expressed`, avec deux garde-fous
    que la version nationale n'a pas besoin d'avoir — ici les tranches sont bien
    plus creuses :

    - les tranches de moins de `min_draws` tirages sont écartées. Une probabilité
      estimée sur vingt simulations a un écart-type de plus de dix points : elle
      afficherait du bruit comme un signal ;
    - `simulations` est renvoyée, pour que l'appelant puisse montrer sur combien
      de tirages chaque point repose.

    Les tranches portent sur les non-exprimés de CETTE circonscription, corrélés
    à 0,91 avec le niveau national. Lire la courbe comme un effet local propre
    serait donc une erreur : elle décrit surtout ce que devient la
    circonscription quand la participation NATIONALE bouge.
    """
    votes = simulation_results[:, district_index, PARTY_SLICE]
    winners = votes.argmax(axis=1)
    non_expressed = simulation_results[:, district_index, ABS_INDEX] / inscrits * 100
    contenders = [k for k in range(len(FAMILIES)) if votes[:, k].max() > 0]

    frame = pl.DataFrame(
        {
            "tranche_basse": np.floor(non_expressed).astype(np.int64),
            "winner": winners,
        }
    )
    rows = []
    for (tranche,), group in frame.group_by("tranche_basse", maintain_order=True):
        if group.height < min_draws:
            continue
        won = group.get_column("winner").to_numpy()
        for k in contenders:
            rows.append(
                {
                    "parti": str(FAMILIES[k]),
                    "tranche_basse": int(tranche),
                    "non_exprimés": float(tranche) + 0.5,
                    "probabilite": float((won == k).mean() * 100),
                    "simulations": group.height,
                }
            )
    schema = {
        "parti": pl.String,
        "tranche_basse": pl.Int64,
        "non_exprimés": pl.Float64,
        "probabilite": pl.Float64,
        "simulations": pl.Int64,
    }
    if not rows:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(rows, schema=schema).sort(["parti", "tranche_basse"])


def district_expressed_rate(cube: np.ndarray, index: int, inscrits: int) -> pl.Series:
    return pl.Series(
        "expressed_share", 100 - cube[:, index, ABS_INDEX] / inscrits * 100
    )
