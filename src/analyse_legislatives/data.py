"""Chargement des résultats électoraux et construction des objets du domaine."""

from collections.abc import Iterable
import csv
import json
from pathlib import Path
from typing import NamedTuple

import polars as pl

from analyse_legislatives.circonscription import Circonscription, CirconscriptionResult
from analyse_legislatives.config import DATA_DIR, PARTY_FAMILIES_PATH
from analyse_legislatives.parties import FAMILIES, NON_EXPRIMES


class FirstRoundData(NamedTuple):
    """Données du premier tour consommées par le modèle et l'application."""

    districts: list[CirconscriptionResult]
    circonscriptions_by_id: dict[str, Circonscription]
    first_round_seats: dict[str, int]
    inscrits_by_id: dict[str, int]
    decided_results_by_id: dict[str, pl.DataFrame]


class SecondRoundResult(NamedTuple):
    """Résultat réel du second tour, agrégé par famille politique."""

    inscrits: int
    exprimes: int
    votes: dict[str, int]

    @property
    def non_exprimes(self) -> int:
        """Abstentions, bulletins blancs et bulletins nuls."""
        return self.inscrits - self.exprimes


def district_ids(districts: Iterable[CirconscriptionResult]) -> list[str]:
    """Identifiants des circonscriptions dans l'ordre reçu."""
    return [district.circonscription.id for district in districts]


def nuance_to_family(path: Path = PARTY_FAMILIES_PATH) -> dict[str, str]:
    """Charge l'unique correspondance entre nuances officielles et familles."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_second_round_results(
    data_dir: Path = DATA_DIR,
) -> dict[str, SecondRoundResult]:
    """Charge les résultats réels, réservés à l'évaluation du modèle."""
    families = nuance_to_family()
    path = data_dir / "raw/legislatives2024/legislatives-2024-resultats-t2.csv"
    results = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            votes: dict[str, int] = {}
            for index in (1, 2, 3, 4):
                nuance = row.get(f"Nuance candidat {index}")
                if not nuance:
                    continue
                family = families[nuance]
                votes[family] = votes.get(family, 0) + int(row[f"Voix {index}"])
            results[row["Code circonscription législative"]] = SecondRoundResult(
                inscrits=int(row["Inscrits"]),
                exprimes=int(row["Exprimés"]),
                votes=votes,
            )
    return results


def _complete_votes(rows: pl.DataFrame) -> dict:
    values = dict(rows.select("GroupPol", "NbVoix").iter_rows())
    return {party: int(values.get(party.value, 0)) for party in FAMILIES} | {
        NON_EXPRIMES: 0
    }


def load_full_results(data_dir: Path = DATA_DIR) -> FirstRoundData:
    """Charge le premier tour prétraité et construit les circonscriptions."""
    path = data_dir / "processed/legislatives2024/data.csv"
    data = pl.read_csv(path, infer_schema_length=None)

    mapping = nuance_to_family()
    mapping_frame = pl.DataFrame(
        {"CodNuaCand": list(mapping), "mapped_family": list(mapping.values())}
    )
    data = (
        data.join(mapping_frame, on="CodNuaCand", how="left")
        .drop("GroupPol")
        .rename({"mapped_family": "GroupPol"})
    )
    unknown = (
        data.filter(pl.col("GroupPol").is_null())
        .get_column("CodNuaCand")
        .unique()
        .sort()
        .to_list()
    )
    if unknown:
        raise ValueError(f"Nuances sans famille dans le mapping : {unknown}.")

    decided_ids = (
        data.filter(pl.col("Elu") == "OUI")
        .get_column("CodCirElec")
        .unique(maintain_order=True)
        .to_list()
    )
    first_round_seats = dict(
        data.filter(pl.col("Elu") == "OUI")
        .group_by("GroupPol")
        .len(name="seats")
        .select("GroupPol", "seats")
        .iter_rows()
    )

    district_level = data.unique("CodCirElec", keep="first", maintain_order=True)
    inscrits_by_id = dict(district_level.select("CodCirElec", "Inscrits").iter_rows())
    # HYPOTHÈSE 1 du billet : abstentions, bulletins blancs et bulletins nuls
    # sont une seule et même catégorie, `NON_EXPRIMES`. Le modèle ne distingue
    # jamais un abstentionniste d'un votant blanc.
    non_expressed_by_id = dict(
        district_level.select(
            "CodCirElec",
            (pl.col("Abstentions") + pl.col("Blancs") + pl.col("Nuls")).alias(
                "non_exprimes"
            ),
        ).iter_rows()
    )
    expressed_by_id = dict(district_level.select("CodCirElec", "Exprimes").iter_rows())

    decided_results = {}
    for district_id in decided_ids:
        expressed = expressed_by_id[district_id]
        decided_results[district_id] = (
            data.filter(pl.col("CodCirElec") == district_id)
            .group_by("GroupPol")
            .agg(
                pl.col("NbVoix").sum().alias("Voix"),
                pl.when((pl.col("Elu") == "OUI").any())
                .then(pl.lit("OUI"))
                .otherwise(pl.lit("NON"))
                .alias("Elu"),
            )
            .with_columns(
                (pl.col("Voix") / expressed * 100).round(1).alias("% exprimés")
            )
            .sort("Voix", descending=True)
        )

    grouped = data.with_columns(
        pl.col("NbVoix").sum().over(["CodCirElec", "GroupPol", "valid_round_two"])
    ).unique(
        ["CodCirElec", "GroupPol", "valid_round_two"],
        keep="first",
        maintain_order=True,
    )
    circonscriptions = {
        district_id: Circonscription(district_id, name)
        for district_id, name in data.select("CodCirElec", "LibCirElec")
        .unique("CodCirElec", maintain_order=True)
        .iter_rows()
    }
    simulated_ids = (
        grouped.filter(
            pl.col("valid_round_two") & ~pl.col("CodCirElec").is_in(decided_ids)
        )
        .get_column("CodCirElec")
        .unique(maintain_order=True)
        .to_list()
    )

    districts = []
    for district_id in simulated_ids:
        rows = grouped.filter(pl.col("CodCirElec") == district_id)
        competing = _complete_votes(rows.filter("valid_round_two"))
        eliminated = _complete_votes(rows.filter(~pl.col("valid_round_two")))
        districts.append(
            CirconscriptionResult(
                circonscriptions[district_id],
                competing,
                eliminated,
                int(non_expressed_by_id[district_id]),
            )
        )

    return FirstRoundData(
        districts=districts,
        circonscriptions_by_id=circonscriptions,
        first_round_seats={
            str(key): int(value) for key, value in first_round_seats.items()
        },
        inscrits_by_id={str(key): int(value) for key, value in inscrits_by_id.items()},
        decided_results_by_id=decided_results,
    )
