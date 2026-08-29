"""Modèle national + local avec corrélation continue par noyau."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import norm as _norm_dist

from analyse_legislatives.circonscription import CirconscriptionResult
from analyse_legislatives.models.base import SimulationParameters
from analyse_legislatives.models.copula import CopulaModel
from analyse_legislatives.parties import FAMILIES, Destination

KERNEL_JITTER = 1e-6
"""Ajout diagonal garantissant que le noyau reste défini positif malgré les
erreurs d'arrondi, pour que la décomposition de Cholesky aboutisse."""


@dataclass
class KernelModel(CopulaModel):
    """
    Corrélation continue entre circonscriptions via un copule gaussien, dont la
    covariance est un noyau de similarité calculé sur les résultats du 1er tour
    (deux circonscriptions politiquement proches au 1er tour ont des reports
    corrélés au 2nd). Un facteur national est mélangé au champ local sur l'échelle
    gaussienne latente : les chocs communs ne s'annulent donc pas dans l'agrégat,
    sans modifier les lois marginales utilisées pour construire chaque ligne.

    HYPOTHÈSE 6 du billet (`writeup.fr.md`) : on ne sait pas dans quel SENS une
    circonscription s'écartera de la moyenne, mais deux circonscriptions
    politiquement proches au 1er tour s'en écarteront dans le même sens. Relâche
    l'hypothèse 5 de `NationalModel`.
    """

    kernel_bandwidth: float | None = None
    mixing_weight: float | None = None

    _cholesky_cache: np.ndarray | None = field(default=None, init=False, repr=False)
    _cached_district_ids: tuple | None = field(default=None, init=False, repr=False)
    _resolved_kernel_bandwidth: float | None = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.mixing_weight is not None and not 0 <= self.mixing_weight <= 1:
            raise ValueError("`mixing_weight` doit appartenir à [0, 1].")

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
        """
        sq_dists = self._squared_distances(districts)
        h = bandwidth if bandwidth is not None else self._median_bandwidth(sq_dists)
        return np.exp(-sq_dists / (2 * h**2))

    def _get_cholesky(self, districts: Sequence[CirconscriptionResult]) -> np.ndarray:
        """Décomposition de Cholesky du noyau gaussien de corrélation entre
        circonscriptions. Mise en cache : ne dépend que des résultats du 1er tour
        (fixes), donc calculée une seule fois et réutilisée à chaque simulation."""
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

        kernel = np.exp(-sq_dists / (2 * bandwidth**2))
        kernel += KERNEL_JITTER * np.eye(len(districts))
        cholesky = np.linalg.cholesky(kernel)

        self._cached_district_ids = district_ids
        self._cholesky_cache = cholesky
        return cholesky

    def kernel_bandwidth_for(self, districts: Sequence[CirconscriptionResult]) -> float:
        """Bande passante effectivement utilisée — soit `kernel_bandwidth` si
        fournie explicitement, soit la valeur résolue par heuristique de la médiane
        sinon (voir `_get_cholesky`)."""
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
        n = len(districts)
        cholesky = self._get_cholesky(districts)
        national_weight = self._national_weight_for(draw)

        uniforms = {}
        for target_party in targets:
            national = self.rng.standard_normal()
            local = cholesky @ self.rng.standard_normal(n)  # $L\eps\sim N(0, K)
            z = (
                np.sqrt(national_weight) * national
                + np.sqrt(1 - national_weight) * local
            )
            uniforms[target_party] = _norm_dist.cdf(z)
        return uniforms
