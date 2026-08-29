"""
Application Streamlit : projections du 2nd tour, nationale et par circonscription.

Ce fichier ne contient que la mise en page et le câblage. Le modèle est dans
`analyse_legislatives.models`, ses hyperparamètres dans `config/model.yaml`, la
boucle Monte-Carlo dans `.simulation`, les agrégations dans `.projections`, les
graphiques dans `.viz.charts` et le texte de méthodologie dans `.viz.methodology`.

Les simulations sont produites hors ligne par ``scripts/reproduce.py``. L'app
charge l'artefact validé qui en résulte et ne fait que des agrégations légères.

Usage : `streamlit run app.py`
"""

import hashlib

import altair as alt
import polars as pl
import streamlit as st

from analyse_legislatives import projections, simulation
from analyse_legislatives.app_artifacts import (
    AppArtifact,
    AppArtifactError,
    load_app_artifact,
)
from analyse_legislatives.data import FirstRoundData, load_full_results as _load
from analyse_legislatives.config import (
    APP_ARTIFACT_DIR,
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
)
from analyse_legislatives.models import DEFAULT_MODEL
from analyse_legislatives.parties import NON_EXPRIMES, SPECTRUM_LABELS
from analyse_legislatives.viz import color_for, format_interval, format_number
from analyse_legislatives.viz.charts import (
    bin_series,
    render_district_wins_vs_non_expressed_chart,
    render_dominant_party_chart,
    render_duel_charts,
    render_expressed_share_chart,
    render_hemicycle,
    render_seats_vs_non_expressed_chart,
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
    """Empreinte de `config/model.yaml`, comparée au manifeste de l'artefact.

    Une divergence arrête l'app : la VM ne doit jamais recalculer silencieusement
    un cube produit sous une autre configuration."""
    return hashlib.sha256(MODEL_CONFIG_PATH.read_bytes()).hexdigest()


@st.cache_resource(show_spinner="Chargement des simulations précalculées…")
def deployed_artifact(digest: str, ids: tuple[str, ...]) -> AppArtifact:
    """Ressource immuable partagée entre toutes les sessions de la VM."""
    return load_app_artifact(
        APP_ARTIFACT_DIR,
        expected_model=DEFAULT_MODEL,
        expected_seed=DEFAULT_SEED,
        expected_n_simulations=DEFAULT_N_SIMUS,
        expected_config_sha256=digest,
        expected_district_ids=ids,
    )


@st.cache_data(show_spinner=False)
def national_seats(digest: str, ids: tuple[str, ...]) -> pl.DataFrame:
    return projections.seats_by_simulation(
        deployed_artifact(digest, ids).cube,
        first_round_data().first_round_seats,
    )


@st.cache_data(show_spinner=False)
def national_expressed_share(digest: str, ids: tuple[str, ...]) -> pl.Series:
    data = first_round_data()
    return projections.expressed_share_by_simulation(
        deployed_artifact(digest, ids).cube,
        data.districts,
        data.inscrits_by_id,
    )


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
    with st.container(horizontal_alignment="center"):
        # Streamlit plafonne cette largeur à celle du parent sur petit écran.
        st.altair_chart(render_hemicycle(median_seats), width=760)


st.set_page_config(page_title="Législatives 2024 — projections", layout="wide")
st.title("Élections législatives 2024 : modélisation du 2nd tour")
st.caption(
    "Modélisation simplifiée des reports de voix (voir le README du dépôt pour la "
    "méthodologie)."
)

first_round = first_round_data()
artifact_ids = tuple(d.circonscription.id for d in first_round.districts)
digest = config_digest()
try:
    artifact = deployed_artifact(digest, artifact_ids)
except AppArtifactError as exc:
    st.error(str(exc))
    st.stop()
cube = artifact.cube
district_index = {d.circonscription.id: i for i, d in enumerate(first_round.districts)}

tab_national, tab_circo, tab_methodo = st.tabs(
    ["Projection nationale", "Projection par circonscription", "Méthodologie"],
    key="main_tab",
    on_change="rerun",
)

with tab_national:
    seats_by_simu = national_seats(digest, artifact_ids)
    st.subheader("Projection des sièges")
    render_seat_panel(seats_by_simu)

    st.subheader("Qui arrive en tête ?")
    st.caption(
        "Probabilité d'être l'unique premier groupe en sièges, sur les mêmes "
        "tirages que ci-dessus. Les égalités sont comptées à part."
    )
    st.altair_chart(render_dominant_party_chart(seats_by_simu), width="stretch")

    st.subheader("Participation simulée")
    expressed_by_simu = national_expressed_share(digest, artifact_ids)
    with st.container(border=True):
        col_metric, col_chart = st.columns([1, 2], vertical_alignment="center")
        with col_metric:
            st.metric(
                "Taux de suffrages exprimés national simulé (2nd tour)",
                f"{expressed_by_simu.median():.1f} %",
                format_interval(expressed_by_simu, " %"),
                delta_color="off",
            )
        with col_chart:
            st.altair_chart(
                render_expressed_share_chart(
                    bin_series(expressed_by_simu),
                    "Distribution des suffrages exprimés nationaux simulés",
                ),
                width="stretch",
            )

    st.subheader("Sensibilité de la projection à la participation")
    conditional_prediction = projections.conditional_seats_by_non_expressed(
        seats_by_simu, expressed_by_simu
    )
    non_expressed_selection = alt.selection_point(
        name="non_expressed_bin",
        fields=["tranche_basse", "tranche_haute"],
        on="click",
        clear="dblclick",
        empty=False,
    )
    with st.container(border=True):
        st.caption(
            "Chaque point agrège les simulations situées dans une tranche d'un "
            "point de non-exprimés et montre leur nombre médian de sièges. Cliquez "
            "un point pour afficher juste dessous la projection correspondante ; "
            "double-cliquez pour réinitialiser."
        )
        non_expressed_event = st.altair_chart(
            render_seats_vs_non_expressed_chart(
                conditional_prediction, non_expressed_selection
            ),
            width="stretch",
            on_select="rerun",
            key="seats_vs_non_expressed",
        )
        selected_bins = list(
            non_expressed_event.selection.get("non_expressed_bin") or []
        )

        if selected_bins:
            lo = selected_bins[0]["tranche_basse"]
            hi = selected_bins[0]["tranche_haute"]
            non_expressed_by_simu = 100 - expressed_by_simu
            selected = (non_expressed_by_simu >= lo) & (non_expressed_by_simu < hi)
            conditional_seats = seats_by_simu.filter(selected)

            st.markdown(f"**Projection pour {lo:.0f} à {hi:.0f} % de non-exprimés**")
            st.caption(
                f"{len(conditional_seats)} simulations sur {len(seats_by_simu)}."
            )
            render_seat_panel(conditional_seats)
        else:
            st.caption("Sélectionnez un point du graphique pour détailler sa tranche.")

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
        # Les graphiques Altair attendent un format long. Ne matérialiser que
        # la circonscription affichée évite une table nationale de 8 M de lignes.
        circo_df = simulation.to_long_frame(cube[:, index : index + 1, :], [district])

        col_table, col_chart = st.columns([2, 3])

        with col_table:
            winner_color = color_for(party_a)
            st.html(
                f"""
                <style>
                .st-key-district_winner {{
                    background: color-mix(in srgb, {winner_color} 18%, transparent);
                    border: 1px solid color-mix(in srgb, {winner_color} 45%, transparent);
                    border-left: 0.35rem solid {winner_color};
                    border-radius: 0.5rem;
                    padding: 0.75rem 1rem 0.5rem;
                }}
                </style>
                """
            )
            with st.container(key="district_winner"):
                st.metric(
                    "Vainqueur le plus probable",
                    party_a,
                    f"{summary['% de victoires'][0]:.0f}% des simulations",
                    delta_color="off",
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
                    "Scénario simulé le plus représentatif (pas des médianes indépendantes)"
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
                    render_duel_charts(
                        circo_df,
                        party_left,
                        party_right,
                        party_a,
                        party_b,
                        f"{party_left} / {party_right} / Non exprimé — {choice}",
                        f"Écart {party_a} vs {party_b} — {choice}",
                    ),
                    width="stretch",
                    key="duel_margin_linked",
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
                "tirages au minimum ; les tranches plus creuses sont écartées)."
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


if tab_methodo.open:
    with tab_methodo:
        render_methodology(
            artifact.prior_matrix,
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
