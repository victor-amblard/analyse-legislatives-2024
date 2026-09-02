"""Modèle national + local avec corrélation continue par noyau."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import norm as _norm_dist

from analyse_legislatives.circonscription import CirconscriptionResult
from analyse_legislatives.config import DEFAULT_BLOCK_CORRELATION_PRIOR
from analyse_legislatives.models.base import SimulationParameters
from analyse_legislatives.models.copula import CopulaModel
from analyse_legislatives.models.ordinal import extension_ranks
from analyse_legislatives.utils.validation import check_beta_pair
from analyse_legislatives.parties import FAMILIES, Destination

KERNEL_JITTER = 1e-6
"""Ajout diagonal garantissant que le noyau reste défini positif malgré les
erreurs d'arrondi, pour que la décomposition de Cholesky aboutisse."""


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

    Reste à dire ce que « semblable » veut dire — c'est `kernel_similarity` :

    - `"departement"` (défaut) : deux circonscriptions du même département ont des
      écarts locaux corrélés à `rho`, les autres ne partagent que la composante
      nationale. La similarité est administrative, connue d'avance, et n'utilise
      AUCUN résultat électoral. `rho` est tiré à chaque simulation dans un prior
      Beta calibré sur le PREMIER tour (voir `block_correlation_prior`).
    - `"hellinger"` : noyau gaussien sur la distance de Hellinger entre
      compositions du 1er tour, la version historique du modèle.

    Le choix n'est pas neutre et n'est pas vérifiable ex ante. A posteriori, le
    variogramme des résidus (`scripts/analyses/residual_variogram.py`) ne retrouve
    pas dans les données la dépendance que la similarité de Hellinger postule sur
    les scores (0,00-0,05 observé contre 0,28-0,42 prédit), alors qu'il met en
    évidence un net regroupement départemental sur la participation (+0,42).
    """

    kernel_bandwidth: float | None = None
    mixing_weight: float | None = None
    kernel_similarity: str = "departement"

    block_correlation_prior: tuple[float, float] = DEFAULT_BLOCK_CORRELATION_PRIOR
    """Prior de `rho`, la corrélation intra-département des écarts locaux.

    Un noyau bloc binaire (`rho = 1`) affirmerait que deux circonscriptions du
    même département dévient à l'identique : le variogramme du premier tour en
    mesure plutôt 0,47 (métropole, paires politiquement éloignées) à 0,77 (France
    entière). Le prior par défaut couvre cette plage sans la figer."""

    block_correlation: float | None = None
    """Valeur imposée de `rho`, pour les analyses de sensibilité. `None` = tirée."""

    _cholesky_cache: np.ndarray | None = field(default=None, init=False, repr=False)
    _cached_district_ids: tuple | None = field(default=None, init=False, repr=False)
    _resolved_kernel_bandwidth: float | None = field(
        default=None, init=False, repr=False
    )
    _drawn_block_correlation: float | None = field(
        default=None, init=False, repr=False
    )
    _departement_index_cache: np.ndarray | None = field(
        default=None, init=False, repr=False
    )
    _cached_departement_ids: tuple | None = field(default=None, init=False, repr=False)

    SIMILARITIES = ("departement", "hellinger")

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.mixing_weight is not None and not 0 <= self.mixing_weight <= 1:
            raise ValueError("`mixing_weight` doit appartenir à [0, 1].")
        if self.kernel_similarity not in self.SIMILARITIES:
            raise ValueError(
                f"`kernel_similarity` inconnue : {self.kernel_similarity!r}. "
                f"Choix possibles : {', '.join(self.SIMILARITIES)}."
            )
        check_beta_pair(self.block_correlation_prior, "block_correlation_prior")
        if self.block_correlation is not None and not 0 <= self.block_correlation <= 1:
            raise ValueError("`block_correlation` doit appartenir à [0, 1].")

    def _begin_simulation(
        self,
        districts: Sequence[CirconscriptionResult],
        draw: SimulationParameters,
    ) -> None:
        """Tire `rho` une fois par simulation, partagé par toutes les lignes."""
        super()._begin_simulation(districts, draw)
        self._drawn_block_correlation = None
        self.block_correlation_for()

    def block_correlation_for(self) -> float:
        """`rho` de la simulation en cours : imposé, déjà tiré, ou tiré ici.

        Le repli sur un tirage à la volée sert aux appels isolés — tests et
        diagnostics appellent les champs latents sans passer par une simulation
        complète.
        """
        if self.block_correlation is not None:
            return float(self.block_correlation)
        if self._drawn_block_correlation is None:
            self._drawn_block_correlation = float(
                self.rng.beta(*self.block_correlation_prior)
            )
        return self._drawn_block_correlation

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

        Les deux derniers caractères numérotent la circonscription DANS le
        département : `'0101'` -> `'01'`, `'2A01'` -> `'2A'`, `'98802'` -> `'988'`
        pour les circonscriptions des Français de l'étranger.
        """
        return district.circonscription.id[:-2]

    def _departement_matrix(
        self, districts: Sequence[CirconscriptionResult]
    ) -> np.ndarray:
        """Noyau bloc atténué : `rho` dans le département, 0 en dehors, 1 sur la
        diagonale.

        `K = rho B + (1 - rho) I` reste semi-défini positif pour tout `rho` de
        [0, 1], `B` étant la matrice d'appartenance au département. Hors du
        département, la corrélation latente totale n'est pas nulle pour autant :
        elle vaut `lambda`, la part nationale.
        """
        index = self._departement_index(districts)
        block = (index[:, None] == index[None, :]).astype(float)
        rho = self.block_correlation_for()
        return rho * block + (1 - rho) * np.eye(len(codes))

    @staticmethod
    def _district_embedding(district: CirconscriptionResult) -> np.ndarray:
        """Vecteur des parts de voix du 1er tour (7 familles + abstention), qui sert
        de position de la circonscription dans « l'espace politique » pour le noyau
        de corrélation. Aucun apprentissage : ce sont les scores bruts."""
        competing_total = sum(
            district.competing_parties_results.get(p, 0) for p in FAMILIES
        )
        eliminated_total = sum(
            district.eliminated_parties_results.get(p, 0) for p in FAMILIES
        )
        total = competing_total + eliminated_total + district.non_expressed

        shares = [
            (
                district.competing_parties_results.get(p, 0)
                + district.eliminated_parties_results.get(p, 0)
            )
            / total
            for p in FAMILIES
        ]
        shares.append(district.non_expressed / total)
        return np.array(shares)

    @staticmethod
    def _median_bandwidth(sq_dists: np.ndarray) -> float:
        """
        Heuristique de la médiane : bande passante = distance de Hellinger médiane
        entre paires distinctes de circonscriptions.

        Elle n'est pas définie s'il n'existe aucune paire (une seule
        circonscription), ni si toutes les circonscriptions sont identiques
        (médiane nulle, donc division par zéro dans le noyau). Dans ces deux cas le
        noyau vaut 1 partout quelle que soit la bande passante — toutes les
        circonscriptions sont parfaitement corrélées — donc n'importe quelle valeur
        strictement positive convient et 1.0 fait l'affaire. Sans ce garde-fou,
        `np.median` d'un tableau vide renvoie NaN et la décomposition de Cholesky
        échoue sur « Matrix is not positive definite ».
        """
        pairs = sq_dists[np.triu_indices_from(sq_dists, k=1)]
        if pairs.size == 0:
            return 1.0
        bandwidth = float(np.median(np.sqrt(pairs)))
        return bandwidth if bandwidth > 0 else 1.0

    def _squared_distances(
        self, districts: Sequence[CirconscriptionResult]
    ) -> np.ndarray:
        """Distances de Hellinger au carré entre compositions du premier tour.

        Pour deux vecteurs de parts ``p`` et ``q`` :

            H²(p, q) = 1/2 * sum((sqrt(p_i) - sqrt(q_i))²)
        """
        embeddings = np.array([self._district_embedding(d) for d in districts])
        sqrt_parts = np.sqrt(embeddings)
        diffs = sqrt_parts[:, None, :] - sqrt_parts[None, :, :]
        return 0.5 * (diffs**2).sum(axis=-1)

    def kernel_matrix_for(
        self,
        districts: Sequence[CirconscriptionResult],
        bandwidth: float | None = None,
    ) -> np.ndarray:
        """
        Noyau gaussien BRUT (sans le jitter numérique ajouté avant la décomposition
        de Cholesky dans `_get_cholesky`), à la bande passante donnée ou, à défaut,
        celle résolue par heuristique de la médiane.

        Exposé pour l'analyse spectrale hors simulation (`scripts/analyses/kernel_spectrum.py`)
        : le jitter n'a de sens que pour stabiliser une décomposition de Cholesky, pas
        pour une décomposition en valeurs propres.

        `bandwidth` ne concerne que la similarité de Hellinger : le noyau
        départemental n'a pas de portée à régler, et l'argument y est ignoré.
        """
        if self.kernel_similarity == "departement":
            return self._departement_matrix(districts)
        sq_dists = self._squared_distances(districts)
        h = bandwidth if bandwidth is not None else self._median_bandwidth(sq_dists)
        return np.exp(-sq_dists / (2 * h**2))

    def _get_cholesky(self, districts: Sequence[CirconscriptionResult]) -> np.ndarray:
        """Décomposition de Cholesky du noyau gaussien de corrélation entre
        circonscriptions. Mise en cache : ne dépend que des résultats du 1er tour
        (fixes), donc calculée une seule fois et réutilisée à chaque simulation."""
        self._require_hellinger("_get_cholesky")
        district_ids = tuple(d.circonscription.id for d in districts)
        cached = self._cholesky_cache
        if self._cached_district_ids == district_ids and cached is not None:
            return cached

        sq_dists = self._squared_distances(districts)
        bandwidth = (
            self.kernel_bandwidth
            if self.kernel_bandwidth is not None
            else self._median_bandwidth(sq_dists)
        )
        self._resolved_kernel_bandwidth = bandwidth

        kernel = self.kernel_matrix_for(districts, bandwidth=bandwidth)
        kernel += KERNEL_JITTER * np.eye(len(districts))
        cholesky = np.linalg.cholesky(kernel)

        self._cached_district_ids = district_ids
        self._cholesky_cache = cholesky
        return cholesky

    def _require_hellinger(self, what: str) -> None:
        """Refuse les objets propres au noyau de Hellinger sous un autre noyau.

        La bande passante et la décomposition de Cholesky n'ont de sens que pour
        une similarité continue. Sous le noyau départemental, la matrice dépend de
        `rho`, tiré à chaque simulation : un Cholesky mis en cache sur les seules
        circonscriptions serait périmé dès le tirage suivant. Mieux vaut une erreur
        explicite qu'un objet silencieusement faux.
        """
        if self.kernel_similarity != "hellinger":
            raise ValueError(
                f"{what} n'a de sens qu'avec `kernel_similarity='hellinger'` ; "
                f"ce modèle utilise {self.kernel_similarity!r}."
            )

    def kernel_bandwidth_for(self, districts: Sequence[CirconscriptionResult]) -> float:
        """Bande passante effectivement utilisée — soit `kernel_bandwidth` si
        fournie explicitement, soit la valeur résolue par heuristique de la médiane
        sinon (voir `_get_cholesky`). Réservée à la similarité de Hellinger."""
        self._get_cholesky(districts)
        bandwidth = self._resolved_kernel_bandwidth
        # `_get_cholesky` vient de la poser ; le contrôle satisfait le typage et
        # attraperait une future réécriture qui oublierait de le faire.
        if bandwidth is None:
            raise RuntimeError("bande passante non résolue")
        return bandwidth

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
        de structure exploitable. Pour le noyau départemental, `K` vaut `rho` dans
        le bloc et 0 dehors, ce qui s'échantillonne exactement — et bien plus vite —
        par un effet départemental partagé :

            z_c = sqrt(rho) g_dept(c) + sqrt(1 - rho) eps_c

        avec `g` et `eps` standard normales indépendantes. La variance vaut 1, la
        covariance intra-département `rho`, et 0 entre départements : c'est
        exactement `K(rho)`, sans décomposition.
        """
        n = len(districts)
        if self.kernel_similarity == "hellinger":
            return self._get_cholesky(districts) @ self.rng.standard_normal(n)

        rho = self.block_correlation_for()
        index = self._departement_index(districts)
        shared = self.rng.standard_normal(index.max() + 1)
        return np.sqrt(rho) * shared[index] + np.sqrt(1 - rho) * self.rng.standard_normal(n)

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
        return (
            np.sqrt(national_weight) * national
            + np.sqrt(1 - national_weight) * self._local_latent_field(districts)
        )

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
