"""
Construit `data/processed/legislatives2024/data.csv` à partir des fichiers bruts.

Cette étape vivait dans `archive/notebooks/0-pretraitement.ipynb`, donc hors du
code exécutable : la table que consomme tout le modèle ne pouvait pas être
reconstruite depuis `data/raw/`. Elle est ici pour que la chaîne complète —
données brutes du ministère → table simulable → résultats publiés — soit
reproductible d'un bout à l'autre.

Deux informations sont ajoutées aux résultats du 1er tour :

- `GroupPol`, la famille politique de chaque nuance (`config/party_families.json`) ;
- `valid_round_two`, qui dit si le candidat était effectivement sur le bulletin du
  2nd tour. C'est là que sont encodés les DÉSISTEMENTS, et c'est la seule
  information postérieure au 1er tour dont le modèle a besoin : il projette un
  bulletin donné, il ne prédit pas qui se retire.

Usage :
    python scripts/prepare_data.py
    python scripts/prepare_data.py --check   # vérifie sans réécrire
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from analyse_legislatives.config import DATA_DIR, PARTY_FAMILIES_PATH, PROJECT_ROOT

FIRST_ROUND_PATH = (
    DATA_DIR
    / "raw/legislatives2024/lg2024-resultats-circonscriptions-une-ligne-par-candidat2.xlsx"
)
"""Le classeur, et non le CSV du même nom : ce dernier n'est pas en UTF-8 et son
décodage dépend de la locale, ce qui est exactement ce qu'un prétraitement
reproductible ne doit pas laisser au hasard."""

SECOND_ROUND_CANDIDATES_PATH = (
    DATA_DIR
    / "raw/legislatives2024/legislatives-2024-candidatures-france-entiere-tour-2-2024-07-03-15h37.csv"
)
OUTPUT_PATH = DATA_DIR / "processed/legislatives2024/data.csv"

NAME_FIXES = {
    ("VÉZIÈS", None): ("VEZIES", None),
    ("JEANDENAND", None): (None, "Florianne"),
    ("FOSSEY", None): (None, "Veronique"),
    ("CLEMENT", None): ("CLÉMENT", None),
}
"""Orthographes divergentes entre le fichier des candidatures et celui des
résultats. Corrections reprises telles quelles du notebook d'origine ; le
rapprochement échoue bruyamment si l'une devient inutile ou insuffisante."""


def district_key(departement: pd.Series, circonscription: pd.Series) -> pd.Series:
    """Clé `CodCirElec` du fichier des résultats, reconstruite depuis le fichier
    des candidatures : code département sur deux caractères, puis le numéro de
    circonscription sur deux chiffres (« 1 » + « 01 » -> « 0101 »)."""
    return departement.str.zfill(2) + circonscription.str[-2:]


def load_second_round_candidates() -> pd.DataFrame:
    raw = pd.read_csv(SECOND_ROUND_CANDIDATES_PATH, sep=";", dtype=str)
    candidates = pd.DataFrame(
        {
            "CodCirElec": district_key(
                raw["Code département"], raw["Code circonscription"]
            ),
            "NomPsn": raw["Nom du candidat"],
            "PrenomPsn": raw["Prénom du candidat"],
        }
    )
    for (nom, prenom), (new_nom, new_prenom) in NAME_FIXES.items():
        match = pd.Series(True, index=candidates.index)
        if nom is not None:
            match &= candidates["NomPsn"] == nom
        if prenom is not None:
            match &= candidates["PrenomPsn"] == prenom
        if new_nom is not None:
            candidates.loc[match, "NomPsn"] = new_nom
        if new_prenom is not None:
            candidates.loc[match, "PrenomPsn"] = new_prenom
    return candidates


def build() -> pd.DataFrame:
    results = pd.read_excel(FIRST_ROUND_PATH, dtype={"CodCirElec": str})

    families = json.loads(PARTY_FAMILIES_PATH.read_text(encoding="utf-8"))
    results["GroupPol"] = results["CodNuaCand"].map(families)
    unknown = sorted(results.loc[results["GroupPol"].isna(), "CodNuaCand"].unique())
    if unknown:
        raise ValueError(f"Nuances absentes de {PARTY_FAMILIES_PATH.name} : {unknown}.")

    candidates = load_second_round_candidates()

    # Le rapprochement porte sur (circonscription, nom, prénom) et NON sur le seul
    # nom : deux candidats homonymes se présentaient dans des circonscriptions
    # différentes, et une jointure par nom seul qualifiait pour le 2nd tour un
    # candidat éliminé au 1er (VALLON Jean-Paul, DVD, 0702 — voir tests).
    key = ["CodCirElec", "NomPsn", "PrenomPsn"]
    merged = results.merge(
        candidates.assign(matched=True), on=key, how="left", validate="1:1"
    )
    merged["valid_round_two"] = merged.pop("matched").notna()

    # Un candidat ne peut être sur le bulletin du 2nd tour sans avoir été qualifié
    # au 1er. C'est exactement l'invariant que violait la jointure par nom seul, et
    # il ne coûte rien à vérifier à chaque construction.
    impossible = merged[merged["valid_round_two"] & (merged["Elu"] != "QUALIF T2")]
    if not impossible.empty:
        raise ValueError(
            "Candidats présents au 2nd tour sans qualification au 1er :\n"
            + impossible[["CodCirElec", "NomPsn", "PrenomPsn", "Elu"]].to_string(
                index=False
            )
        )

    matched = int(merged["valid_round_two"].sum())
    if matched != len(candidates):
        missing = candidates.merge(results[key], on=key, how="left", indicator=True)
        orphans = missing.loc[missing["_merge"] == "left_only", key]
        raise ValueError(
            f"{len(candidates) - matched} candidats du 2nd tour sans ligne de 1er "
            f"tour correspondante :\n{orphans.to_string(index=False)}"
        )
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare à la table existante sans la réécrire",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()

    data = build()
    qualified = int((data["Elu"] == "QUALIF T2").sum())
    print(
        f"{len(data)} candidats du 1er tour | {qualified} qualifiés pour le 2nd tour "
        f"| {int(data['valid_round_two'].sum())} après désistements"
    )

    if args.check:
        if not args.output.exists():
            sys.exit(f"{args.output} n'existe pas : rien à comparer.")
        existing = pd.read_csv(args.output, index_col=0, dtype={"CodCirElec": str})
        common = [c for c in data.columns if c in existing.columns]
        differences = (
            data[common]
            .reset_index(drop=True)
            .compare(existing[common].reset_index(drop=True))
        )
        if differences.empty:
            print("identique à la table existante")
        else:
            print(f"{len(differences)} lignes diffèrent :")
            print(differences.to_string())
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(args.output)
    print(f"wrote {args.output.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
