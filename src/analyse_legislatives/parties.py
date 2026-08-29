from enum import StrEnum
from typing import Literal


class PoliticalFamily(StrEnum):
    NFPx = "NFP+"
    LR = "LR"
    RNx = "RN+"
    ENSx = "ENS+"
    DIV = "DIV"
    DVG = "DVG"
    DVD = "DVD"


NON_EXPRIMES: Literal["NON_EXPRIMES"] = "NON_EXPRIMES"

type Destination = PoliticalFamily | Literal["NON_EXPRIMES"]

DESTINATIONS: tuple[Destination, ...] = tuple(PoliticalFamily) + (NON_EXPRIMES,)

SPECTRUM_ORDER: tuple[PoliticalFamily, ...] = (
    PoliticalFamily.DIV,
    PoliticalFamily.NFPx,
    PoliticalFamily.DVG,
    PoliticalFamily.ENSx,
    PoliticalFamily.LR,
    PoliticalFamily.DVD,
    PoliticalFamily.RNx,
)


FAMILIES: tuple[PoliticalFamily, ...] = tuple(PoliticalFamily)
SPECTRUM_LABELS: list[str] = [str(party) for party in SPECTRUM_ORDER]


def label(destination: Destination) -> str:
    return str(destination)


DESTINATION_LABELS: list[str] = [label(destination) for destination in DESTINATIONS]
