"""Modèle national + local avec corrélation continue par noyau."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import norm as _norm_dist

from analyse_legislatives.circonscription import CirconscriptionResult
from analyse_legislatives.config import (
    DEFAULT_DEPARTMENT_CORRELATION_PRIOR,
    DEFAULT_REGION_CORRELATION_PRIOR,
)
from analyse_legislatives.models.base import SimulationParameters
from analyse_legislatives.models.copula import CopulaModel
from analyse_legislatives.models.ordinal import extension_ranks
from analyse_legislatives.utils.validation import check_beta_pair
from analyse_legislatives.parties import Destination

DEPARTMENTS_BY_REGION = {
    "Auvergne-Rhône-Alpes": "01,03,07,15,26,38,42,43,63,69,73,74",
    "Bourgogne-Franche-Comté": "21,25,39,58,70,71,89,90",
    "Bretagne": "22,29,35,56",
    "Centre-Val de Loire": "18,28,36,37,41,45",
    "Corse": "2A,2B",
    "Grand Est": "08,10,51,52,54,55,57,67,68,88",
    "Hauts-de-France": "02,59,60,62,80",
    "Île-de-France": "75,77,78,91,92,93,94,95",
    "Normandie": "14,27,50,61,76",
    "Nouvelle-Aquitaine": "16,17,19,23,24,33,40,47,64,79,86,87",
    "Occitanie": "09,11,12,30,31,32,34,46,48,65,66,81,82",
    "Pays de la Loire": "44,49,53,72,85",
    "Provence-Alpes-Côte d'Azur": "04,05,06,13,83,84",
}

DEPARTMENT_TO_REGION = {
    dept: region
    for region, depts in DEPARTMENTS_BY_REGION.items()
    for dept in depts.split(",")
}


def department_group(district_id: str) -> str:
    """Return the geographic group used for the department-level effect.

    The final two characters normally identify a constituency inside a
    department. ``ZZ`` instead groups all French citizens abroad, whose eleven
    constituencies cover unrelated areas. They therefore get separate local
    groups and share only the national factor.
    """
    return district_id if district_id.startswith("ZZ") else district_id[:-2]


@dataclass
class KernelModel(CopulaModel):
    """
    Corrélation entre circonscriptions via un copule gaussien. Un facteur national
    est mélangé au champ local sur l'échelle gaussienne latente : les chocs communs
    ne s'annulent donc pas dans l'agrégat, sans modifier les lois marginales
    utilisées pour construire chaque ligne.

    HYPOTHÈSE 6 du billet (`writeup.fr.md`) : on ne sait pas dans quel SENS une
    circonscription s'écartera de la moyenne, mais deux circonscriptions SEMBLABLES
    s'en écarteront dans le même sens. Relâche l'hypothèse 5 de `NationalModel`.

    Le noyau est emboîté à deux échelles. Deux circonscriptions du même
    département ont leurs écarts locaux corrélés à `rho_departement` ; deux
    circonscriptions d'une même région mais de départements différents le sont à
    `rho_region` (`<= rho_departement`) ; les autres ne partagent que la
    composante nationale. Ces appartenances administratives sont connues à
    l'avance et n'utilisent aucun résultat électoral.

    L'emboîtement lui-même répond à un constat du même ordre : restreint au seul
    département, le noyau ne touche qu'environ 1 % des paires de circonscriptions
    de France — trop peu pour peser sur l'incertitude nationale, quasiment comme
    l'indépendance pure. Le variogramme du premier tour montre que la corrélation
    ne s'arrête pas à la frontière du département : elle décroît par PALIERS avec
    l'échelle géographique (+0,47 même département, +0,28 même région sans le
    même département, -0,09 régions différentes, sur les paires politiquement
    éloignées). Le niveau régional n'est pas une hypothèse gratuite : il est
    demandé par les mêmes données qui ont justifié le département.
    """

    mixing_weight: float | None = None

    department_correlation_prior: tuple[float, float] = (
        DEFAULT_DEPARTMENT_CORRELATION_PRIOR
    )
    region_correlation_prior: tuple[float, float] = DEFAULT_REGION_CORRELATION_PRIOR
    department_correlation: float | None = None
    region_correlation: float | None = None

    _drawn_department_correlation: float | None = field(
        default=None, init=False, repr=False
    )
    _drawn_region_correlation: float | None = field(
        default=None, init=False, repr=False
    )
    _departement_index_cache: np.ndarray | None = field(
        default=None, init=False, repr=False
    )
    _cached_departement_ids: tuple | None = field(default=None, init=False, repr=False)
    _region_index_cache: np.ndarray | None = field(default=None, init=False, repr=False)
    _cached_region_ids: tuple | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.mixing_weight is not None and not 0 <= self.mixing_weight <= 1:
            raise ValueError("`mixing_weight` doit appartenir à [0, 1].")
        check_beta_pair(
            self.department_correlation_prior, "department_correlation_prior"
        )
        check_beta_pair(self.region_correlation_prior, "region_correlation_prior")
        if (
            self.department_correlation is not None
            and not 0 <= self.department_correlation <= 1
        ):
            raise ValueError("`department_correlation` doit appartenir à [0, 1].")
        if (
            self.region_correlation is not None
            and not 0 <= self.region_correlation <= 1
        ):
            raise ValueError("`region_correlation` doit appartenir à [0, 1].")

    def _begin_simulation(
        self,
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> None:
        """Tire les deux `rho` une fois par simulation, partagés par toutes les
        lignes. Le département d'abord : la région en a besoin pour son
        plafonnement."""
        super()._begin_simulation(districts, draw)
        self._drawn_department_correlation = None
        self._drawn_region_correlation = None
        self.region_correlation_for(self.department_correlation_for())

    def department_correlation_for(self) -> float:
        """`rho_departement` de la simulation en cours : imposé, déjà tiré, ou
        tiré ici.

        Le repli sur un tirage à la volée sert aux appels isolés — tests et
        diagnostics appellent les champs latents sans passer par une simulation
        complète.
        """
        if self.department_correlation is not None:
            return float(self.department_correlation)
        if self._drawn_department_correlation is None:
            self._drawn_department_correlation = float(
                self.rng.beta(*self.department_correlation_prior)
            )
        return self._drawn_department_correlation

    def region_correlation_for(self, department_correlation: float) -> float:
        """`rho_region` de la simulation en cours, plafonné par `rho_departement`.

        Les deux niveaux sont tirés dans des priors INDÉPENDANTS, calibrés
        séparément sur les deux paliers mesurés par le variogramme du premier
        tour, puis on impose `rho_region = min(tirage, rho_departement)` : une
        région ne peut pas être plus corrélée que le département qui la compose.
        Le plafond ne mord que rarement, puisque les deux priors sont déjà centrés
        dans le bon ordre — c'est un garde-fou, pas le moteur de la contrainte.
        """
        if self.region_correlation is not None:
            raw = float(self.region_correlation)
        else:
            if self._drawn_region_correlation is None:
                self._drawn_region_correlation = float(
                    self.rng.beta(*self.region_correlation_prior)
                )
            raw = self._drawn_region_correlation
        return min(raw, department_correlation)

    def _departement_index(
        self, districts: Sequence[CirconscriptionResult]
    ) -> np.ndarray:
        """Index entier du département de chaque circonscription, mis en cache."""
        district_ids = tuple(d.circonscription.id for d in districts)
        if self._cached_departement_ids == district_ids:
            cached = self._departement_index_cache
            if cached is not None:
                return cached
        codes = [self._departement(d) for d in districts]
        _, index = np.unique(codes, return_inverse=True)
        self._cached_departement_ids = district_ids
        self._departement_index_cache = index
        return index

    @staticmethod
    def _departement(district: CirconscriptionResult) -> str:
        """Code du département, déduit de l'identifiant de la circonscription.

        Les deux derniers caractères numérotent généralement la circonscription
        DANS le département : `'0101'` -> `'01'`, `'2A01'` -> `'2A'`,
        `'98802'` -> `'988'`. Les identifiants `ZZ01` à `ZZ11` restent distincts,
        car `ZZ` n'est pas un département.
        """
        return department_group(district.circonscription.id)

    def _region_index(self, districts: Sequence[CirconscriptionResult]) -> np.ndarray:
        """Index entier de la région de chaque circonscription, mis en cache.

        Pour un territoire ultramarin non couvert, région et département
        coïncident : aucun supplément régional ne s'applique. Les Français de
        l'étranger sont déjà séparés par `department_group` et restent donc
        indépendants au niveau local.
        """
        district_ids = tuple(d.circonscription.id for d in districts)
        if self._cached_region_ids == district_ids:
            cached = self._region_index_cache
            if cached is not None:
                return cached
        codes = [self._departement(d) for d in districts]
        labels = [DEPARTMENT_TO_REGION.get(code, f"__solo__:{code}") for code in codes]
        _, index = np.unique(labels, return_inverse=True)
        self._cached_region_ids = district_ids
        self._region_index_cache = index
        return index

    def _nested_block_matrix(
        self, districts: Sequence[CirconscriptionResult]
    ) -> np.ndarray:
        """Noyau bloc emboîté : `rho_departement` dans le département,
        `rho_region` dans la région sans le même département, 0 au-delà, 1 sur la
        diagonale.

        `K = rho_region * R + (rho_departement - rho_region) * D + (1 -
        rho_departement) * I`, où `R` et `D` sont les matrices d'appartenance à la
        même région et au même département. Reste semi-défini positif pour tout
        `0 <= rho_region <= rho_departement <= 1` : c'est exactement la structure
        de covariance d'un modèle à effets emboîtés (région, puis département dans
        la région, puis résidu propre à la circonscription) — un cas classique,
        garanti défini positif par construction. Hors de la région, la
        corrélation latente totale n'est pas nulle pour autant : elle vaut
        `lambda`, la part nationale.
        """
        dept_index = self._departement_index(districts)
        region_index = self._region_index(districts)
        same_dept = (dept_index[:, None] == dept_index[None, :]).astype(float)
        same_region = (region_index[:, None] == region_index[None, :]).astype(float)

        rho_dept = self.department_correlation_for()
        rho_region = self.region_correlation_for(rho_dept)

        n = len(districts)
        return (
            rho_region * same_region
            + (rho_dept - rho_region) * same_dept
            + (1 - rho_dept) * np.eye(n)
        )

    def kernel_matrix_for(
        self, districts: Sequence[CirconscriptionResult]
    ) -> np.ndarray:
        """Matrice de covariance locale du noyau région/département."""
        return self._nested_block_matrix(districts)

    def _national_weight_for(self, draw: SimulationParameters) -> float:
        """Lambda effectif : celui du tirage, ou l'override fixe des analyses de
        sensibilité."""
        return draw.mixing_weight if self.mixing_weight is None else self.mixing_weight

    def local_shock_field(
        self, districts: Sequence[CirconscriptionResult]
    ) -> np.ndarray:
        """Chocs locaux corrélés par le noyau : `z = L eps ~ N(0, K)`.

        Le variogramme des résidus montre que la part de suffrages exprimés est
        fortement groupée géographiquement (+0,42 entre circonscriptions d'un même
        département) alors que le modèle la tirait indépendamment. `delta_c`
        emprunte donc la même dépendance que les taux de report.

        Aucun mélange national/local ici, contrairement aux lignes de report : le
        choc commun est déjà représenté par `delta_nat`, et le mélanger une
        seconde fois le compterait deux fois. Comme `diag(K) = 1`, la marginale de
        chaque circonscription reste `N(0, 1)` : seule la dépendance change.
        """
        return self._local_latent_field(districts)

    def _local_extension_ranks(
        self,
        source_party: Destination,
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> tuple[Sequence[Destination], np.ndarray] | None:
        """Départage les ex aequo circonscription par circonscription.

        HYPOTHÈSE 6 appliquée à l'ordre lui-même. Sans cela, le tirage qui
        départage deux destinations laissées ex aequo est national : dans une
        simulation donnée, les 501 circonscriptions décideraient toutes que les
        électeurs `NFP+` préfèrent `LR` à `RN+`, ou toutes le contraire. Or ce
        flou est la principale source d'incertitude du modèle : le laisser
        parfaitement corrélé revient à interdire à cette incertitude-là de varier
        localement.

        Un score latent par destination ex aequo, mélangé national/local comme les
        cellules, puis un tri par circonscription. À circonscription fixée, les
        scores d'un même palier sont i.i.d. : l'ordre obtenu suit donc exactement
        la loi uniforme de `linear_extension` (voir `ordinal.extension_ranks`).
        Seule leur dépendance entre circonscriptions est nouvelle.
        """
        tiers = self.transfer_orderings[source_party]
        if all(len(tier) == 1 for tier in tiers):
            return None  # ordre déjà total : rien à départager

        national_weight = self._national_weight_for(draw)
        scores = {
            target: self._mixed_latent_field(districts, national_weight)
            for tier in tiers
            if len(tier) > 1
            for target in tier
        }
        return extension_ranks(tiers, scores)

    def _sample_row_uniforms(
        self,
        targets: Sequence[Destination],
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> Mapping[Destination, np.ndarray]:
        """
        Pour chaque cellule de la ligne, mélange un tirage national scalaire et un
        champ local dont la covariance est le noyau de similarité du 1er tour :

            z_c = sqrt(lambda) z_nat + sqrt(1-lambda) z_loc,c

        avec z_nat ~ N(0,1), z_loc ~ N(0,K) et lambda tiré une fois par simulation.
        Comme diag(K)=1, chaque z_c reste marginalement N(0,1), à l'ajout
        numérique de 1e-6 près utilisé pour stabiliser Cholesky. Entre deux
        circonscriptions c et c', la covariance latente devient

            lambda + (1-lambda) K[c,c'].

        La fonction de répartition normale transforme ensuite ces variables en
        uniformes sans changer leur copule. Les cellules différentes utilisent des
        facteurs nationaux et locaux indépendants : avant le classement ordinal,
        la normalisation des Gamma conserve donc bien la marginale Dirichlet de
        chaque ligne.
        """
        national_weight = self._national_weight_for(draw)
        return {
            target_party: _norm_dist.cdf(
                self._mixed_latent_field(districts, national_weight)
            )
            for target_party in targets
        }

    def _local_latent_field(
        self, districts: Sequence[CirconscriptionResult]
    ) -> np.ndarray:
        """Champ local `z_loc ~ N(0, K)`, une valeur par circonscription.

        Pour la similarité de Hellinger, il faut passer par Cholesky : `K` n'a pas
        de structure exploitable. Pour le noyau départemental, `K` est EMBOÎTÉ
        (région, puis département dans la région, puis résidu propre), ce qui
        s'échantillonne exactement — et bien plus vite qu'une décomposition —
        par deux effets partagés, régional puis départemental :

            z_c = sqrt(rho_region) g_region(c)
                + sqrt(rho_departement - rho_region) g_dept(c)
                + sqrt(1 - rho_departement) eps_c

        avec `g_region`, `g_dept` et `eps` standard normales indépendantes. La
        variance vaut 1, la covariance intra-département `rho_departement`, la
        covariance intra-région (départements différents) `rho_region`, et 0
        au-delà de la région : c'est exactement `K(rho_departement, rho_region)`,
        sans décomposition.
        """
        rho_dept = self.department_correlation_for()
        rho_region = self.region_correlation_for(rho_dept)
        dept_index = self._departement_index(districts)
        region_index = self._region_index(districts)
        g_region = self.rng.standard_normal(region_index.max() + 1)
        g_dept = self.rng.standard_normal(dept_index.max() + 1)
        eps = self.rng.standard_normal(len(districts))
        return (
            np.sqrt(rho_region) * g_region[region_index]
            + np.sqrt(rho_dept - rho_region) * g_dept[dept_index]
            + np.sqrt(1 - rho_dept) * eps
        )

    def _mixed_latent_field(
        self, districts: Sequence[CirconscriptionResult], national_weight: float
    ) -> np.ndarray:
        """Un champ latent gaussien mélangeant national et local :

            z_c = sqrt(lambda) z_nat + sqrt(1-lambda) z_loc,c

        avec z_nat ~ N(0,1) partagé et z_loc ~ N(0, K). Comme diag(K)=1, chaque
        z_c reste marginalement N(0,1) : tout ce qui est construit à partir de ce
        champ garde donc sa loi marginale et ne gagne QUE de la dépendance.
        """
        national = self.rng.standard_normal()
        return np.sqrt(national_weight) * national + np.sqrt(
            1 - national_weight
        ) * self._local_latent_field(districts)

    def tilts_for_districts(
        self,
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> np.ndarray:
        """Tilt localisé par le même noyau que les lignes de report.

        HYPOTHÈSE 6, appliquée au plus gros réservoir de voix : on ignore si les
        abstentionnistes d'une circonscription donnée se mobilisent plutôt pour le
        candidat en tête ou contre lui, mais deux circonscriptions politiquement
        proches au 1er tour doivent pencher dans le même sens.

        La transformation inverse de la loi uniforme préserve exactement la
        marginale : chaque `t_c` reste distribué selon
        `U(non_expressed_tilt_bounds)`, comme le tilt national qu'il remplace.
        Seule la DÉPENDANCE entre circonscriptions change — et, comme pour les
        reports, une part de la variation locale se compense donc à l'agrégation
        nationale (voir l'analyse de sensibilité à `lambda`).

        `draw.tilt` n'est pas utilisé ici : il reste le tilt des variantes
        nationales, tiré en amont pour que les deux familles de modèles partagent
        le même flux aléatoire jusqu'à ce point.
        """
        z = self._mixed_latent_field(districts, self._national_weight_for(draw))
        low, high = self.non_expressed_tilt_bounds
        return low + (high - low) * _norm_dist.cdf(z)
