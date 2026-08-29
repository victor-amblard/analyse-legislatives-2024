from collections.abc import Sequence
import numpy as np
import polars as pl

from analyse_legislatives.circonscription import CirconscriptionResult
from analyse_legislatives.data import district_ids
from analyse_legislatives.models import Model
from analyse_legislatives.parties import DESTINATIONS
from analyse_legislatives.utils.progress import ProgressCallback
from analyse_legislatives.transfers import TransferMatrix


def run(
    model: Model,
    districts: Sequence[CirconscriptionResult],
    n_simus: int,
    progress: ProgressCallback | None = None,
) -> np.ndarray:
    """
    Cube des simulations, de forme
    `(n_simus, len(districts), len(DESTINATIONS))` et de dtype entier — ce sont
    des voix, pas des parts.

    Le modèle porte son propre générateur aléatoire : rejouer la même séquence
    suppose de le reconstruire (voir `models.build(seed=...)`), pas de rappeler
    cette fonction.
    """

    cube = np.zeros((n_simus, len(districts), len(DESTINATIONS)), dtype=np.int64)
    for i_simu in range(n_simus):
        for i_district, prediction in enumerate(
            model.predict_all_circonscriptions(districts)
        ):
            for i_dest, destination in enumerate(DESTINATIONS):
                cube[i_simu, i_district, i_dest] = prediction.results[destination]
        if progress is not None:
            progress(i_simu + 1, n_simus)
    return cube


def prior_predictive_rates(
    model: Model,
    districts: Sequence[CirconscriptionResult],
    n_simus: int,
    progress: ProgressCallback | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Renvoie deux tableaux, tous deux de forme `(n_simus, n_cells)` avec les
    colonnes de `matrix_cells(model)` :

    - `marginal` : le taux d'UNE circonscription tirée au hasard à chaque
      simulation — la loi marginale du taux d'une circonscription quelconque ;
    - `spread` : l'écart-type du taux ENTRE circonscriptions, par simulation —
      l'hétérogénéité locale qu'implique la variante (identiquement nulle pour
      `national`, qui partage une seule matrice).
    """
    cells = model.matrix_cells
    marginal = np.zeros((n_simus, len(cells)))
    spread = np.zeros((n_simus, len(cells)))

    for i_simu in range(n_simus):
        matrices = model.sample_transfer_matrices(districts)
        rates = np.array(
            [[m.rates[source][target] for source, target in cells] for m in matrices]
        )
        # Une circonscription au hasard, et non la première : sur les variantes
        # corrélées, les circonscriptions ne sont pas interchangeables (leur
        # position dans l'espace politique compte), donc fixer l'indice
        # échantillonnerait la marginale d'une circonscription particulière.
        marginal[i_simu] = rates[model.rng.integers(len(matrices))]
        spread[i_simu] = rates.std(axis=0)
        if progress is not None:
            progress(i_simu + 1, n_simus)

    return marginal, spread


def prior_predictive_median_matrix(
    model: Model,
    districts: Sequence[CirconscriptionResult],
    n_simus: int | None = None,
    progress: ProgressCallback | None = None,
) -> TransferMatrix:
    """
    Matrice des médianes de la prédictive a priori — un résumé lisible du modèle,
    à afficher là où l'on montrait auparavant les taux moyens fixés à la main.

    À lire comme un résumé cellule par cellule, PAS comme un tirage : rien ne
    garantit que la matrice des médianes marginales respecte les ordres de
    préférence ni que ses lignes somment à 1 (voir
    `projections.closest_to_marginal_median` pour le même écueil sur les sièges).
    """
    if n_simus is None:
        from analyse_legislatives.config import DEFAULT_N_SIMUS

        n_simus = DEFAULT_N_SIMUS
    marginal, _ = prior_predictive_rates(model, districts, n_simus, progress)
    medians = np.median(marginal, axis=0)
    rates: dict = {}
    for (source, target), value in zip(model.matrix_cells, medians):
        rates.setdefault(source, {})[target] = float(value)
    return TransferMatrix(rates)


def to_long_frame(
    cube: np.ndarray, districts: Sequence[CirconscriptionResult]
) -> pl.DataFrame:
    """
    Tableau long (id_simu, id_circo, party, votes) attendu par Altair.
    """
    n_simus, n_districts, n_dest = cube.shape
    ids = np.array(district_ids(districts), dtype=object)
    labels = np.array([str(d) for d in DESTINATIONS], dtype=object)
    return pl.DataFrame(
        {
            "id_simu": np.repeat(np.arange(n_simus), n_districts * n_dest),
            "id_circo": np.tile(np.repeat(ids, n_dest), n_simus),
            "party": np.tile(labels, n_simus * n_districts),
            "votes": cube.reshape(-1),
        }
    )
