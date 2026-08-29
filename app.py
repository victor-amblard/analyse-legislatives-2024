"""
Application Streamlit : projections du 2nd tour, nationale et par circonscription.

Ce fichier ne contient que la mise en page et le câblage. Le modèle est dans
`analyse_legislatives.models`, ses hyperparamètres dans `config/model.yaml`, la
boucle Monte-Carlo dans `.simulation`, les agrégations dans `.projections`, les
graphiques dans `.viz.charts` et le texte de méthodologie dans `.viz.methodology`.

Les simulations sont calculées une seule fois (mises en cache par Streamlit) puis
réutilisées par tous les onglets — pas de recalcul à chaque interaction.

Usage : `streamlit run app.py`
"""

import altair as alt
import hashlib

import numpy as np
import polars as pl
import streamlit as st

from analyse_legislatives import projections, simulation
from analyse_legislatives.data import FirstRoundData, load_full_results as _load
from analyse_legislatives.config import (
    DEFAULT_DIRICHLET_ALPHA_BOUNDS,
    DEFAULT_DISTRICT_EXPRESSED_BAND_PTS,
    DEFAULT_EXPECTED_EXPRESSED_CHANGE_PTS,
    DEFAULT_NATIONAL_EXPRESSED_BAND_PTS,
    DEFAULT_NON_EXPRESSED_RETENTION_PRIOR,
    DEFAULT_NON_EXPRESSED_TILT_BOUNDS,
    DEFAULT_QUALIFIED_DEMOBILISATION_PRIOR,
    DEFAULT_N_SIMUS,
    DEFAULT_SEED,
    MODEL_CONFIG_PATH,
    PROJECT_ROOT,
)
from analyse_legislatives.models import DEFAULT_MODEL, build
from analyse_legislatives.transfers import TransferMatrix
from analyse_legislatives.parties import NON_EXPRIMES, SPECTRUM_LABELS
from analyse_legislatives.viz import format_interval, format_number
from analyse_legislatives.viz.charts import (
    bin_series,
    render_district_wins_vs_non_expressed_chart,
    render_dominant_party_chart,
    render_expressed_share_chart,
    render_hemicycle,
    render_margin_chart,
    render_seats_vs_non_expressed_chart,
    render_ternary_chart,
)
from analyse_legislatives.viz.methodology import render as render_methodology


def is_dark() -> bool:
    """Thème actif côté navigateur. Les graphiques importés du billet portent
    leur propre palette et sont affichés avec `theme=None` : c'est donc à eux de
    suivre le thème, Streamlit ne le fera pas à leur place."""
    theme = getattr(st.context, "theme", None)
    return getattr(theme, "type", "light") == "dark"


@st.cache_data(show_spinner="Chargement des résultats du 1er tour…")
def first_round_data() -> FirstRoundData:
    return _load()


@st.cache_data(show_spinner=False)
def config_digest() -> str:
    """Empreinte de `config/model.yaml`, incluse dans la clé du cache disque.

    Sans elle, modifier un prior laisserait l'app resservir indéfiniment un cube
    calculé sous l'ancienne configuration."""
    return hashlib.sha256(MODEL_CONFIG_PATH.read_bytes()).hexdigest()[:16]


CUBE_CACHE_DIR = PROJECT_ROOT / "artifacts/cache"


@st.cache_data(show_spinner=False)
def simulation_cube(model: str, seed: int, n_simus: int, digest: str) -> np.ndarray:
    """Le cube des simulations, conservé sur disque d'une session à l'autre.

    À seed et configuration fixées, ce cube est entièrement déterministe : deux
    exécutions donnent le même tableau au bit près. Le recalculer à chaque
    démarrage faisait attendre ~80 s pour reproduire un résultat déjà connu ; le
    relire prend 0,01 s.

    Cache écrit à la main plutôt que `@st.cache_data(persist="disk")` : cette
    option est un no-op hors d'un vrai runtime Streamlit — la bibliothèque
    bascule alors en silence sur un stockage en mémoire (`No runtime found,
    using MemoryCacheStorageManager`) — donc elle n'est pas vérifiable par un
    test. Un fichier `.npy` l'est.

    La clé est dans le NOM du fichier : changer de modèle, de seed, de nombre de
    tirages ou toucher `config/model.yaml` produit un autre nom, donc jamais de
    relecture périmée. `artifacts/cache/` est déjà ignoré par Git.
    """
    path = CUBE_CACHE_DIR / f"cube-{model}-{seed}-{n_simus}-{digest}.npy"
    if path.exists():
        return np.load(path)

    districts = first_round_data().districts
    bar = st.progress(0.0, text=f"Simulation des reports de voix — 0 / {n_simus}")

    def advance(done: int, total: int) -> None:
        bar.progress(
            done / total, text=f"Simulation des reports de voix — {done} / {total}"
        )

    try:
        cube = simulation.run(
            build(model, seed=seed), districts, n_simus, progress=advance
        )
    finally:
        bar.empty()

    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, cube)
    return cube


@st.cache_data(show_spinner=False)
def predictions_long() -> pl.DataFrame:
    """Vue en tableau long du cube, pour les graphiques Altair par circonscription."""
    return simulation.to_long_frame(
        simulation_cube(DEFAULT_MODEL, DEFAULT_SEED, DEFAULT_N_SIMUS, config_digest()),
        first_round_data().districts,
    )


@st.cache_data(show_spinner=False)
def national_seats() -> pl.DataFrame:
    return projections.seats_by_simulation(
        simulation_cube(DEFAULT_MODEL, DEFAULT_SEED, DEFAULT_N_SIMUS, config_digest()),
        first_round_data().first_round_seats,
    )


@st.cache_data(show_spinner=False)
def national_expressed_share() -> pl.Series:
    data = first_round_data()
    return projections.expressed_share_by_simulation(
        simulation_cube(DEFAULT_MODEL, DEFAULT_SEED, DEFAULT_N_SIMUS, config_digest()),
        data.districts,
        data.inscrits_by_id,
    )


@st.cache_data(show_spinner=False)
def prior_predictive_matrix(model: str, seed: int, digest: str) -> TransferMatrix:
    """Médianes de la prédictive a priori de la matrice de report.

    Le modèle ne contient plus de taux fixés à la main : pour montrer à quoi
    ressemblent les taux qu'il implique, il faut les tirer (voir
    `scripts/analyses/prior_predictive.py`).

    Caché sur disque pour la même raison que le cube, et c'est ici que ça pesait
    le plus : 40 s pour un tableau 8x8 que l'onglet Méthodologie n'affiche que
    résumé. Streamlit exécute le script entier à chaque chargement, onglets non
    affichés compris — ce calcul était donc payé même par qui ne l'ouvrait
    jamais. Stocké dense dans l'ordre canonique `DESTINATIONS`, via l'API
    existante `to_matrix` / `from_matrix`.
    """
    path = CUBE_CACHE_DIR / f"prior-matrix-{model}-{seed}-{digest}.npy"
    if path.exists():
        return TransferMatrix.from_matrix(np.load(path))

    bar = st.progress(0.0, text="Résumé de la prédictive a priori…")
    try:
        matrix = simulation.prior_predictive_median_matrix(
            build(model, seed=seed), first_round_data().districts
        )
    finally:
        bar.empty()

    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, matrix.to_matrix())
    return matrix


def render_seat_metrics(seats_by_simu: pl.DataFrame, median_seats: dict) -> None:
    """Une colonne de métrique par parti : sièges du scénario médian, et
    intervalle à 90% en dessous."""
    for col, party in zip(st.columns(len(SPECTRUM_LABELS)), SPECTRUM_LABELS):
        col.metric(
            party,
            format_number(median_seats[party]),
            format_interval(seats_by_simu[party], decimals=0),
            delta_color="off",
        )


def render_seat_panel(seats_by_simu: pl.DataFrame) -> None:
    """Métriques par parti + hémicycle du scénario le plus représentatif."""
    median_seats = projections.median_scenario_seats(seats_by_simu)
    render_seat_metrics(seats_by_simu, median_seats)
    st.columns(3)[1].altair_chart(render_hemicycle(median_seats), width="content")


st.set_page_config(page_title="Législatives 2024 — projections", layout="wide")
st.title("Projections du 2nd tour — élections législatives 2024")
st.caption(
    "Modélisation simplifiée des reports de voix (voir le README du dépôt pour la "
    "méthodologie). NOTE : ces projections ne constituent pas des sondages au sens "
    "de la loi du 19 juillet 1977."
)

# L'ordre compte : Streamlit rend les éléments de haut en bas. Titre, onglets et
# emplacement de la barre sont créés AVANT la simulation, pour que la page soit
# déjà là — et la progression visible — pendant les ~80 s du premier calcul.
progress_slot = st.container()

first_round = first_round_data()
with progress_slot:
    cube = simulation_cube(
        DEFAULT_MODEL, DEFAULT_SEED, DEFAULT_N_SIMUS, config_digest()
    )
district_index = {d.circonscription.id: i for i, d in enumerate(first_round.districts)}

tab_national, tab_circo, tab_methodo = st.tabs(
    ["Projection nationale", "Projection par circonscription", "Méthodologie"]
)

with tab_national:
    seats_by_simu = national_seats()
    render_seat_panel(seats_by_simu)

    st.divider()
    st.subheader("Qui arrive en tête ?")
    st.caption(
        "Probabilité d'être l'unique premier groupe en sièges, sur les mêmes "
        "tirages que ci-dessus. Les égalités sont comptées à part."
    )
    st.altair_chart(render_dominant_party_chart(seats_by_simu), width="stretch")

    st.divider()
    expressed_by_simu = national_expressed_share()
    col_metric, col_chart = st.columns([1, 2])
    with col_metric:
        st.metric(
            "Taux de suffrages exprimés national simulé (2nd tour)",
            f"{expressed_by_simu.median():.1f} %",
            format_interval(expressed_by_simu, " %"),
            delta_color="off",
        )
    with col_chart:
        expressed_selection = alt.selection_point(
            name="expressed_bin",
            fields=["bin_low", "bin_high"],
            on="click",
            clear="dblclick",
            empty=False,
        )
        expressed_event = st.altair_chart(
            render_expressed_share_chart(
                bin_series(expressed_by_simu),
                "Distribution des suffrages exprimés nationaux simulés "
                "(cliquer une barre pour voir les sièges conditionnels)",
                expressed_selection,
            ),
            width="stretch",
            on_select="rerun",
            key="expressed_hist_national",
        )

    selected_bins = list(expressed_event.selection.get("expressed_bin") or [])

    st.subheader("Sièges conditionnellement au niveau de non-exprimés")
    st.caption(
        "Chaque point agrège les simulations situées dans une tranche d'un point "
        "de pourcentage et montre leur nombre médian de sièges. Dans le "
        "modèle, les non-exprimés regroupent abstention, votes blancs et votes nuls ; "
        "les sièges incluent ceux acquis dès le 1er tour."
    )
    conditional_prediction = projections.conditional_seats_by_non_expressed(
        seats_by_simu, expressed_by_simu
    )
    st.altair_chart(
        render_seats_vs_non_expressed_chart(conditional_prediction),
        width="stretch",
        key="seats_vs_non_expressed",
    )

    st.divider()
    if selected_bins:
        lo, hi = selected_bins[0]["bin_low"], selected_bins[0]["bin_high"]
        selected = (expressed_by_simu >= lo) & (expressed_by_simu <= hi)
        conditional_seats = seats_by_simu.filter(selected)
    else:
        conditional_seats = None

    if conditional_seats is not None and len(conditional_seats) > 0:
        st.subheader("Sièges conditionnels au niveau de suffrages exprimés sélectionné")
        st.caption(
            f"Suffrages exprimés entre {lo:.1f} % et {hi:.1f} % "
            f"({len(conditional_seats)} simulations sur {len(seats_by_simu)}) — "
            "double-cliquer sur l'histogramme pour réinitialiser."
        )
        render_seat_panel(conditional_seats)
    elif selected_bins:
        st.warning(
            "Aucune simulation dans ce bin — cliquez une autre barre de l'histogramme."
        )
    else:
        st.caption(
            "Cliquez une barre de l'histogramme des suffrages exprimés ci-dessus pour "
            "voir la distribution des sièges conditionnelle à ce niveau."
        )

with tab_circo:
    options = {
        f"{c.id} — {c.name}": c.id
        for c in sorted(first_round.circonscriptions_by_id.values(), key=lambda c: c.id)
    }
    choice = st.selectbox("Circonscription", options.keys())
    id_circo = options[choice]

    st.subheader(choice)

    if id_circo in first_round.decided_results_by_id:
        st.info(
            "Circonscription pourvue dès le 1er tour — pas de 2nd tour à simuler. "
            "Résultats du 1er tour :"
        )
        result_table = (
            first_round.decided_results_by_id[id_circo]
            .rename({"GroupPol": "Parti", "Elu": "Élu"})
            .with_columns(
                pl.col("Voix").map_elements(format_number, return_dtype=pl.String)
            )
        )
        st.dataframe(result_table, width="stretch", hide_index=True)

    else:
        index = district_index[id_circo]
        district = first_round.districts[index]
        n_competing = district.n_competing()
        # Les graphiques par circonscription (triangle, écart de voix) supposent
        # un duel ; au-delà de 2 qualifiés ils sont remplacés par un message.
        is_duel = n_competing <= 2

        summary = projections.district_summary(cube, index)
        party_a, party_b = summary["parti"][:2].to_list()

        display_table = summary.with_columns(
            *[
                pl.col(column).map_elements(format_number, return_dtype=pl.String)
                for column in ["moyenne", "p05", "mediane", "p95"]
            ],
            pl.col("% de victoires").map_elements(
                lambda value: f"{value:.1f} %", return_dtype=pl.String
            ),
        )

        district_inscrits = first_round.inscrits_by_id[id_circo]
        expressed_rate = projections.district_expressed_rate(
            cube, index, district_inscrits
        )
        # Tableau long restreint à cette circonscription : seul format que
        # comprennent les graphiques Altair.
        long_df = predictions_long()
        circo_df = long_df.filter(pl.col("id_circo") == id_circo)

        col_table, col_chart = st.columns([2, 3])

        with col_table:
            st.metric(
                "Vainqueur le plus probable",
                party_a,
                f"{summary['% de victoires'][0]:.0f}% des simulations",
            )
            st.dataframe(display_table, width="stretch")

            st.metric(
                "Taux de suffrages exprimés médian simulé",
                f"{expressed_rate.median():.1f} %",
                format_interval(expressed_rate, " %"),
                delta_color="off",
            )

            if is_duel:
                median_scenario = projections.median_scenario_district(
                    circo_df, party_a, party_b
                )
                exprimes = median_scenario[party_a] + median_scenario[party_b]
                st.caption(
                    "Scénario simulé le plus représentatif (pas des médianes indépendantes) "
                    "— % exprimés pour les partis, % inscrits pour les suffrages exprimés"
                )
                col_a, col_b, col_abs = st.columns(3)
                col_a.metric(
                    f"{party_a} (exprimés)",
                    f"{median_scenario[party_a] / exprimes * 100:.1f} %",
                )
                col_b.metric(
                    f"{party_b} (exprimés)",
                    f"{median_scenario[party_b] / exprimes * 100:.1f} %",
                )
                col_abs.metric(
                    "Suffrages exprimés (inscrits)",
                    f"{100 - median_scenario[NON_EXPRIMES] / district_inscrits * 100:.1f} %",
                )
            else:
                st.caption(
                    f"{n_competing} candidats qualifiés : le détail du scénario médian par "
                    "parti n'est calculé que pour les duels (voir le graphique ci-contre)."
                )

        with col_chart:
            if is_duel:
                party_left, party_right = sorted(
                    [party_a, party_b], key=SPECTRUM_LABELS.index
                )
                st.altair_chart(
                    render_ternary_chart(
                        circo_df,
                        party_left,
                        party_right,
                        f"{party_left} / {party_right} / Non exprimé — {choice}",
                    ),
                    width="stretch",
                )
                st.altair_chart(
                    render_margin_chart(
                        circo_df,
                        party_a,
                        party_b,
                        f"Écart {party_a} vs {party_b} — {choice}",
                    ),
                    width="stretch",
                )
            else:
                race_type = {3: "triangulaire", 4: "quadrangulaire"}.get(
                    n_competing, f"{n_competing} candidats"
                )
                st.info(
                    f"Cette circonscription est une **{race_type}** ({n_competing} candidats "
                    "qualifiés) : les graphiques habituellement affichés ici (triangle, écart "
                    "de voix) supposent un duel à 2 candidats et ne représenteraient correctement "
                    "que 2 des candidats en lice — graphe non supporté pour cette configuration. "
                    "Le tableau ci-contre (médiane/quantiles par parti) reste valide pour chacun "
                    "des candidats."
                )

        st.divider()
        st.subheader("Victoire selon le niveau de non-exprimés")
        conditional_wins = projections.conditional_wins_by_non_expressed(
            cube, index, district_inscrits
        )
        if conditional_wins.is_empty():
            st.caption(
                "Trop peu de simulations par tranche d'un point pour estimer une "
                "probabilité de victoire dans cette circonscription."
            )
        else:
            st.altair_chart(
                render_district_wins_vs_non_expressed_chart(
                    conditional_wins,
                    f"Probabilité de victoire par niveau de non-exprimés — {choice}",
                ),
                width="stretch",
                key="district_wins_vs_non_expressed",
            )
            low = int(conditional_wins["simulations"].min())
            st.caption(
                "Chaque point regroupe les simulations dont les non-exprimés de "
                f"cette circonscription tombent dans une tranche d'un point ({low} "
                "tirages au minimum ; les tranches plus creuses sont écartées). "
                "**Attention à la lecture** : les non-exprimés locaux sont corrélés "
                "à 0,91 avec le niveau national, donc cette courbe montre surtout ce "
                "que devient la circonscription quand la participation NATIONALE "
                "bouge — pas un effet local propre. Et c'est une relation interne au "
                "modèle, pas un effet causal identifié : dans trois circonscriptions "
                "sur quatre elle est plate."
            )


@st.cache_resource(show_spinner="Construction des figures de méthodologie…")
def prior_simplex_chart(dark: bool):
    """La SEULE figure du billet importable telle quelle : elle ne dépend que des
    ordres déclarés dans `config/model.yaml`, donc d'aucune projection, donc elle
    ne peut pas contredire les tirages de l'app.

    Les graphiques de projection du billet (`dominant_party`, `joint_seats`)
    lisent `artifacts/publication/models/` : les afficher ici montrerait des chiffres
    en désaccord avec les autres onglets dès que la graine ou un hyperparamètre
    change. La probabilité d'être premier groupe est donc RECALCULÉE sur le cube
    de l'app (voir `render_dominant_party_chart`) plutôt qu'importée.

    Le balayage de sensibilité au noyau a quitté cet onglet : il porte sur
    `kernel_anchored`, pas sur le modèle par défaut que cette page décrit.
    Il reste produit par `scripts/analyses/kernel_sensitivity.py` et commenté dans le billet.
    """
    from analyse_legislatives.publication.charts import simplex_chart

    return simplex_chart(dark=dark)


with tab_methodo:
    render_methodology(
        prior_predictive_matrix(DEFAULT_MODEL, DEFAULT_SEED, config_digest()),
        non_expressed_retention_prior=DEFAULT_NON_EXPRESSED_RETENTION_PRIOR,
        qualified_demobilisation_prior=DEFAULT_QUALIFIED_DEMOBILISATION_PRIOR,
        expected_expressed_change_pts=DEFAULT_EXPECTED_EXPRESSED_CHANGE_PTS,
        national_expressed_band_pts=DEFAULT_NATIONAL_EXPRESSED_BAND_PTS,
        district_expressed_band_pts=DEFAULT_DISTRICT_EXPRESSED_BAND_PTS,
        non_expressed_tilt_bounds=DEFAULT_NON_EXPRESSED_TILT_BOUNDS,
        dirichlet_alpha_bounds=DEFAULT_DIRICHLET_ALPHA_BOUNDS,
        n_simus=DEFAULT_N_SIMUS,
        seed=DEFAULT_SEED,
    )

    st.subheader("D'un ordre de préférence à une distribution")
    st.caption(
        "Ce que le prior autorise pour une ligne de la matrice, dans un duel "
        "ENS+/RN+. La région délimitée est celle que l'ordre déclaré rend "
        "compatible ; α gouverne la concentration à l'intérieur."
    )
    st.altair_chart(prior_simplex_chart(is_dark()), theme=None, width="stretch")
