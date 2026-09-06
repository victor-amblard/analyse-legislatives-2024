"""
L'ordre canonique et la nature des clés.

Ces tests semblent triviaux ; ils gardent l'invariant qui a motivé la création de
`parties.py` : l'axe des matrices était redéclaré dans cinq fichiers, dans des
ordres différents, ce qui rendait toute matrice ambiguë sans savoir d'où elle
venait.
"""

from analyse_legislatives.config import (
    DEFAULT_FREE_TARGETS,
    DEFAULT_TRANSFER_ORDERINGS,
)
from analyse_legislatives.parties import (
    NON_EXPRIMES,
    DESTINATIONS,
    FAMILIES,
    SPECTRUM_ORDER,
    PoliticalFamily,
)


def test_destinations_are_the_families_plus_abstention():
    assert tuple(PoliticalFamily) + (NON_EXPRIMES,) == DESTINATIONS
    assert len(DESTINATIONS) == len(FAMILIES) + 1
    assert (
        DESTINATIONS[-1] == NON_EXPRIMES
    ), "NON_EXPRIMES doit rester en dernier (indexée par -1)"


def test_spectrum_covers_every_family_exactly_once():
    assert set(SPECTRUM_ORDER) == set(FAMILIES)
    assert len(SPECTRUM_ORDER) == len(FAMILIES)


def test_abstention_sits_in_the_least_preferred_tier():
    """L'abstention est placée DANS le dernier palier, à égalité avec le ou les
    partis les moins préférés — pas dans un palier à part en dessous d'eux. Le modèle
    ne tranche donc pas entre s'abstenir et voter pour le parti le plus hostile."""
    for source, tiers in DEFAULT_TRANSFER_ORDERINGS.items():
        assert (
            NON_EXPRIMES in tiers[-1]
        ), f"NON_EXPRIMES doit être dans le dernier palier de {source}"
        assert len(tiers[-1]) > 1, (
            f"NON_EXPRIMES ne doit pas être SEULE dans le dernier palier de {source} : elle "
            "est ex aequo avec le parti le moins préféré, pas en dessous de lui"
        )
        listed = [target for tier in tiers[:-1] for target in tier]
        assert (
            NON_EXPRIMES not in listed
        ), f"NON_EXPRIMES ne doit apparaître qu'une fois dans {source}"


def test_each_ordering_lists_every_rankable_destination_once():
    """Les ordres couvrent exactement les destinations CLASSABLES : ni la source
    elle-même, ni les destinations libres (NON_EXPRIMES, DIV), dont on ne déclare pas le
    rang."""
    for source, tiers in DEFAULT_TRANSFER_ORDERINGS.items():
        listed = [target for tier in tiers for target in tier]
        expected = set(DESTINATIONS) - {source} - set(DEFAULT_FREE_TARGETS)
        assert len(listed) == len(set(listed)), f"doublon dans l'ordre de {source}"
        assert set(listed) == expected, f"ordre de {source} incomplet"


def test_free_targets_are_never_ranked():
    """NON_EXPRIMES et DIV n'ont pas de rang déclaré : les classer serait une affirmation
    gratuite (rien ne dit qu'un électeur ENS+ préfère un candidat divers au RN+)."""
    for source, tiers in DEFAULT_TRANSFER_ORDERINGS.items():
        listed = {target for tier in tiers for target in tier}
        assert not (listed & set(DEFAULT_FREE_TARGETS)), f"ligne {source}"


def test_every_family_is_a_source():
    """DIV et les divers ont beau être libres en DESTINATION, ils restent des
    sources : leurs réservoirs doivent bien se redistribuer."""
    assert set(DEFAULT_TRANSFER_ORDERINGS) == set(FAMILIES)
