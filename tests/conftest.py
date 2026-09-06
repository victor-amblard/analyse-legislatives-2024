"""Fixtures partagées : de petites circonscriptions synthétiques, pour que les
tests ne dépendent ni des fichiers de données ni de leur contenu."""

import pytest

from analyse_legislatives.circonscription import Circonscription, CirconscriptionResult
from analyse_legislatives.parties import NON_EXPRIMES, DESTINATIONS, PoliticalFamily
from analyse_legislatives.transfers import TransferMatrix


def make_district(
    competing: dict,
    eliminated: dict | None = None,
    non_expressed: int = 1000,
    id: str = "01",
) -> CirconscriptionResult:
    """
    Construit une circonscription en ne nommant que les partis concernés.

    Les dictionnaires sont complétés à l'ordre canonique complet, comme le fait
    `data.load_full_results` : c'est une précondition du modèle, et un test qui
    l'ignorerait passerait à côté des bugs d'indexation.
    """
    return CirconscriptionResult(
        Circonscription(id, f"Circonscription {id}"),
        {d: competing.get(d, 0) for d in DESTINATIONS},
        {d: (eliminated or {}).get(d, 0) for d in DESTINATIONS},
        non_expressed,
    )


@pytest.fixture
def duel():
    """Duel NFP+ / RN+, avec un réservoir ENS+ éliminé et de l'abstention."""
    return make_district(
        competing={PoliticalFamily.NFPx: 10_000, PoliticalFamily.RNx: 9_000},
        eliminated={PoliticalFamily.ENSx: 5_000},
        non_expressed=8_000,
    )


@pytest.fixture
def triangulaire():
    return make_district(
        competing={
            PoliticalFamily.NFPx: 10_000,
            PoliticalFamily.RNx: 9_000,
            PoliticalFamily.ENSx: 8_000,
        },
        eliminated={PoliticalFamily.LR: 4_000},
        non_expressed=8_000,
        id="02",
    )


@pytest.fixture
def districts(duel, triangulaire):
    return [duel, triangulaire]


@pytest.fixture
def matrix():
    """Matrice de report simple et asymétrique — des valeurs distinctes pour que
    toute erreur de transposition se voie. Construite par programme : à 7 familles,
    une table écrite à la main serait illisible et se désynchroniserait au moindre
    ajout de famille."""
    rates = {
        source: {
            target: round(0.1 + 0.05 * ((i + j) % 7), 3)
            for j, target in enumerate(PoliticalFamily)
            if target != source
        }
        for i, source in enumerate(PoliticalFamily)
    }
    for party in PoliticalFamily:
        rates[party][NON_EXPRIMES] = 0.1
    rates[NON_EXPRIMES] = {NON_EXPRIMES: 0.9}
    return TransferMatrix(rates)
