"""Static blog charts built with Altair and exported as SVG.

Keep conventional statistical charts here. Bespoke explanatory illustrations
(Sankey, animated simulation, preference chips) live in
``publication.illustrations``.
"""

from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import polars as pl
from scipy.special import expit, logit
from scipy.stats import beta, norm

from analyse_legislatives.config import (
    DEFAULT_DEPARTMENT_CORRELATION_PRIOR,
    DEFAULT_DIRICHLET_ALPHA_BOUNDS,
    DEFAULT_DISTRICT_EXPRESSED_BAND_PTS,
    DEFAULT_EXPECTED_EXPRESSED_CHANGE_PTS,
    DEFAULT_MIXING_PRIOR,
    DEFAULT_NATIONAL_EXPRESSED_BAND_PTS,
    DEFAULT_NON_EXPRESSED_RETENTION_PRIOR,
    DEFAULT_NON_EXPRESSED_TILT_BOUNDS,
    DEFAULT_QUALIFIED_DEMOBILISATION_PRIOR,
    DEFAULT_REGION_CORRELATION_PRIOR,
    DEFAULT_SEED,
    PROJECT_ROOT,
)
from analyse_legislatives.data import load_full_results, nuance_to_family
from analyse_legislatives.parties import label as party_label
from analyse_legislatives.publication.sources import load_pollster_ranges
from analyse_legislatives.viz.palette import chart_palette

OUTPUT_DIR = PROJECT_ROOT / "site/public/figures"
RESULTS_DIR = PROJECT_ROOT / "artifacts/publication/models"
SENSITIVITY_DIR = PROJECT_ROOT / "artifacts/publication/sensitivity"
PRIOR_DIR = PROJECT_ROOT / "artifacts/publication/prior"

MODEL_COLOURS = {
    "National ancré": "#2a78d6",
    "Local ancré": "#b56824",
}

DELTA_EXAMPLE_DRAWS = 20_000
DIRICHLET_SPLIT_ALPHAS = (0.5, 0.75, 1.0)
TILT_EXAMPLE_VALUES = (-1.0, 0.0, 1.0)

# Correpsond aux paramètres du billet
SIMULATION_EXAMPLE_DRAWS = {
    "Concentration α": 0.70,
    "Démobilisation d": 0.04,
    "Rétention des non-exprimés": 0.90,
    "Tilt τ": 0.0,
}
ANCHORED_EXAMPLE_DRAWS = {
    "Concentration α": 0.70,
    "Démobilisation d": 0.04,
    "Rétention des non-exprimés": 0.90,
    "Mélange national λ": 0.60,
    "Tilt τ": 0.0,
    "Dérive nationale δnat": 0.08,
    "Écart local δ0101": -0.04,
    "Corrélation département ρd": 0.70,
    "Corrélation région ρr": 0.30,
}

POLLSTER_PARTY_LABELS = {
    "NFP + DVG": "NFP+ et DVG",
    "ENS and allies": "ENS+ et alliés",
    "LR + DVD": "LR et DVD",
    "RN and allies": "RN+ et alliés",
    "Others": "Autres",
}


def _style(chart: alt.Chart, *, dark: bool = False) -> alt.Chart:
    """Shared restrained theme for static blog exports."""
    ink = "#e9eaee" if dark else "#16181d"
    muted = "#aeb4c0" if dark else "#5a616e"
    grid = "#343944" if dark else "#e3e5ea"
    tick = "#4a505c" if dark else "#dfe2e8"
    return (
        chart.configure_view(stroke=None)
        .configure_axis(
            domain=False,
            gridColor=grid,
            labelColor=muted,
            labelFont="Arial",
            labelFontSize=10,
            tickColor=tick,
            titleColor=ink,
            titleFont="Arial",
            titleFontSize=11,
        )
        .configure_legend(
            labelColor=muted,
            labelFont="Arial",
            labelFontSize=10,
            orient="top-right",
            title=None,
        )
        .configure_header(
            labelColor=ink,
            labelFont="Arial",
            labelFontSize=11,
            titleColor=ink,
            titleFont="Arial",
        )
        .configure_title(
            anchor="start",
            color=ink,
            font="Arial",
            fontSize=16,
            fontWeight=600,
            subtitleColor=muted,
            subtitleFont="Arial",
            subtitleFontSize=11,
        )
        .properties(background="transparent")
    )


def pollster_intervals_chart(*, dark: bool = False) -> alt.Chart:
    """Last published seat ranges compared with the actual result."""
    source = load_pollster_ranges().with_columns(
        pl.col("party").replace(POLLSTER_PARTY_LABELS)
    )
    parties = source.get_column("party").unique(maintain_order=True).to_list()
    pollsters = source.get_column("pollster").unique(maintain_order=True).to_list()
    below = pl.col("actual") < pl.col("low")
    above = pl.col("actual") > pl.col("high")
    data = source.with_columns(
        pl.when(below)
        .then(pl.col("actual"))
        .when(above)
        .then(pl.col("high"))
        .alias("miss_from"),
        pl.when(below)
        .then(pl.col("low"))
        .when(above)
        .then(pl.col("actual"))
        .alias("miss_to"),
        pl.when(below)
        .then(pl.col("low") - pl.col("actual"))
        .when(above)
        .then(pl.col("actual") - pl.col("high"))
        .alias("miss"),
    ).with_columns(((pl.col("miss_from") + pl.col("miss_to")) / 2).alias("miss_mid"))

    y = alt.Y("pollster:N", sort=pollsters, title=None)
    tooltip = [
        alt.Tooltip("party:N", title="Groupe"),
        alt.Tooltip("pollster:N", title="Institut"),
        alt.Tooltip("low:Q", title="Borne basse"),
        alt.Tooltip("high:Q", title="Borne haute"),
        alt.Tooltip("actual:Q", title="Résultat réel"),
    ]
    ranges = (
        alt.Chart(data)
        .mark_rule(
            color="#3987e5" if dark else "#2a78d6",
            strokeWidth=5,
            strokeCap="round",
        )
        .encode(
            x=alt.X("low:Q", title="Sièges", scale=alt.Scale(domain=[0, 230])),
            x2="high:Q",
            y=y,
            tooltip=tooltip,
        )
    )
    gaps = (
        alt.Chart(data)
        .transform_filter("isValid(datum.miss)")
        .mark_rule(color="#d03b3b", strokeWidth=2, strokeDash=[2, 2])
        .encode(x="miss_from:Q", x2="miss_to:Q", y=y)
    )
    gap_labels = (
        alt.Chart(data)
        .transform_filter("isValid(datum.miss)")
        .mark_text(
            color="#d03b3b",
            dy=-8,
            font="Arial",
            fontSize=9,
            fontWeight=600,
        )
        .encode(x="miss_mid:Q", y=y, text=alt.Text("miss:Q", format=".0f"))
    )
    actual = (
        alt.Chart(data)
        .mark_point(
            shape="diamond",
            filled=True,
            size=75,
            color="#e9eaee" if dark else "#16181d",
            stroke="#14161a" if dark else "#fbfbfc",
            strokeWidth=1.5,
        )
        .encode(x="actual:Q", y=y, tooltip=tooltip)
    )
    chart = (
        alt.layer(ranges, gaps, gap_labels, actual)
        .properties(width=580, height=alt.Step(22))
        .facet(
            row=alt.Row(
                "party:N",
                sort=parties,
                title=None,
                header=alt.Header(labelAlign="left", labelAngle=0, labelFontWeight=600),
            ),
            spacing=18,
        )
    )
    return _style(chart, dark=dark)


POLLSTER_BLOCKS = {
    "NFP + DVG": ["NFP+", "DVG"],
    "LR + DVD": ["LR", "DVD"],
    "RN and allies": ["RN+"],
}
"""Blocs dont les deux conventions s'accordent à trois sièges près.

`ENS` et « autres » sont écartés : les découpages y divergent de 15 et 19 sièges,
pour des raisons de nomenclature et non de qualité de prévision. Les inclure
ferait passer une différence de vocabulaire pour un écart de prévision."""

BLOCK_LABELS = {
    "NFP + DVG": "NFP+ et DVG",
    "LR + DVD": "LR et DVD",
    "RN and allies": "RN+ et alliés",
}
COMPARISON_MODELS = {
    "national": "Modèle national",
    "national_anchored": "Modèle national ancré",
    "kernel_anchored": "Modèle local ancré",
}


def _model_block_intervals() -> pl.DataFrame:
    """Intervalles à 90 % des modèles, agrégés dans les blocs des instituts.

    Les blocs sont sommés TIRAGE PAR TIRAGE avant d'en prendre les quantiles :
    additionner les bornes de deux intervalles marginaux donnerait un intervalle
    faux, puisque les sièges des deux familles sont corrélés.
    """
    rows = []
    for model, label in COMPARISON_MODELS.items():
        draws = pl.read_csv(RESULTS_DIR / f"joint-diagnostics-{model}.csv").filter(
            pl.col("role") != "observed"
        )
        for block, families in POLLSTER_BLOCKS.items():
            totals = draws.select(pl.sum_horizontal(families).alias("seats"))["seats"]
            rows.append(
                {
                    "source": label,
                    "kind": "Modèle",
                    "party": block,
                    "low": float(totals.quantile(0.05)),
                    "high": float(totals.quantile(0.95)),
                    "median": float(totals.median()),
                }
            )
    return pl.DataFrame(rows)


def pollster_vs_model_chart(*, dark: bool = False) -> alt.Chart:
    """Fourchettes publiées par les instituts et intervalles à 90 % des modèles."""
    published = load_pollster_ranges().filter(
        pl.col("party").is_in(list(POLLSTER_BLOCKS))
    )
    actual = {
        row["party"]: row["actual"]
        for row in published.select("party", "actual").unique().iter_rows(named=True)
    }
    institutes = published.select(
        pl.col("pollster").alias("source"),
        pl.lit("Institut").alias("kind"),
        "party",
        pl.col("low").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.lit(None, dtype=pl.Float64).alias("median"),
    )
    data = pl.concat([institutes, _model_block_intervals()]).with_columns(
        pl.col("party").replace(BLOCK_LABELS).alias("block"),
        pl.col("party").replace(actual).cast(pl.Float64).alias("actual"),
    )
    order = published.get_column("pollster").unique(maintain_order=True).to_list()
    order += list(COMPARISON_MODELS.values())
    blocks = [BLOCK_LABELS[b] for b in POLLSTER_BLOCKS]

    low = float(data.get_column("low").min()) - 10
    high = float(data.get_column("high").max()) + 10
    y = alt.Y("source:N", sort=order, title=None)
    colour = alt.Color(
        "kind:N",
        title=None,
        scale=alt.Scale(
            domain=["Institut", "Modèle"],
            range=["#3987e5", "#d95926"] if dark else ["#2a78d6", "#eb6834"],
        ),
        legend=alt.Legend(orient="top", direction="horizontal"),
    )
    tooltip = [
        alt.Tooltip("block:N", title="Bloc"),
        alt.Tooltip("source:N", title="Source"),
        alt.Tooltip("low:Q", title="Borne basse"),
        alt.Tooltip("high:Q", title="Borne haute"),
        alt.Tooltip("actual:Q", title="Résultat réel"),
    ]
    ranges = (
        alt.Chart(data)
        .mark_rule(strokeWidth=5, strokeCap="round")
        .encode(
            x=alt.X(
                "low:Q",
                title="Sièges",
                scale=alt.Scale(domain=[low, high], nice=False),
            ),
            x2="high:Q",
            y=y,
            color=colour,
            tooltip=tooltip,
        )
    )
    medians = (
        alt.Chart(data)
        .transform_filter("isValid(datum.median)")
        .mark_point(
            shape="circle",
            filled=True,
            size=28,
            stroke="#14161a" if dark else "#fbfbfc",
            strokeWidth=1.2,
        )
        .encode(x="median:Q", y=y, color=colour, tooltip=tooltip)
    )
    truth = (
        alt.Chart(data)
        .mark_point(
            shape="diamond",
            filled=True,
            size=75,
            color="#e9eaee" if dark else "#16181d",
            stroke="#14161a" if dark else "#fbfbfc",
            strokeWidth=1.5,
        )
        .encode(x="actual:Q", y=y, tooltip=tooltip)
    )
    chart = (
        alt.layer(ranges, medians, truth)
        .properties(width=560, height=alt.Step(21))
        .facet(
            row=alt.Row(
                "block:N",
                sort=blocks,
                title=None,
                header=alt.Header(labelAlign="left", labelAngle=0, labelFontWeight=600),
            ),
            spacing=18,
        )
    )
    return _style(chart, dark=dark)


def withdrawals_chart(*, dark: bool = False) -> alt.Chart:
    """Initially qualified candidates split into retained and withdrawn."""
    data = pd.read_csv(PROJECT_ROOT / "data/processed/legislatives2024/data.csv")
    data["party"] = data["CodNuaCand"].map(nuance_to_family())
    qualified = data[data["Elu"].eq("QUALIF T2")]
    counts = (
        qualified.groupby(["party", "valid_round_two"]).size().unstack(fill_value=0)
    )
    parties = ["NFP+", "DVG", "ENS+", "LR", "DVD", "RN+", "DIV"]
    rows = []
    for party in parties:
        retained = int(counts.loc[party, True]) if party in counts.index else 0
        withdrawn = int(counts.loc[party, False]) if party in counts.index else 0
        rows.append(
            {
                "party": party,
                "retained": retained,
                "withdrawn_start": retained,
                "total": retained + withdrawn,
                "withdrawn": withdrawn,
                "label": f"{withdrawn} / {retained + withdrawn}",
            }
        )
    summary = pd.DataFrame(rows)
    colours = {
        party_label(family): colour
        for family, colour in chart_palette(dark=dark).items()
    }
    y = alt.Y("party:N", sort=parties, title=None)
    tooltip = [
        alt.Tooltip("party:N", title="Groupe"),
        alt.Tooltip("retained:Q", title="Candidats maintenus"),
        alt.Tooltip("withdrawn:Q", title="Désistements"),
        alt.Tooltip("total:Q", title="Initialement qualifiés"),
    ]
    retained = (
        alt.Chart(summary)
        .mark_bar(color="#68707d" if dark else "#aeb3bc", height=14)
        .encode(x=alt.X("retained:Q", title="Candidats"), y=y, tooltip=tooltip)
    )
    withdrawn = (
        alt.Chart(summary)
        .mark_bar(height=14)
        .encode(
            x="withdrawn_start:Q",
            x2="total:Q",
            y=y,
            color=alt.Color(
                "party:N",
                legend=None,
                scale=alt.Scale(
                    domain=parties,
                    range=[colours.get(party, "#777777") for party in parties],
                ),
            ),
            tooltip=tooltip,
        )
    )
    labels = (
        alt.Chart(summary)
        .mark_text(
            align="left",
            dx=6,
            color="#e9eaee" if dark else "#16181d",
            font="Arial",
            fontSize=10,
        )
        .encode(x="total:Q", y=y, text="label:N")
    )
    total_withdrawn = int(summary["withdrawn"].sum())
    chart = alt.layer(retained, withdrawn, labels).properties(
        width=600,
        height=alt.Step(35),
        title=alt.Title(
            f"{total_withdrawn} désistements ont rebattu les cartes du second tour",
            subtitle=(
                "Les candidats maintenus sont en gris ; les segments colorés représentent les désistements. "
                "Les étiquettes indiquent les désistements / candidats initialement qualifiés."
            ),
        ),
    )
    return _style(chart, dark=dark)


def kernel_sensitivity_chart(*, dark: bool = False) -> alt.Chart:
    data = pd.read_csv(SENSITIVITY_DIR / "kernel-rho-lambda.csv")
    data = data[data["party"].isin(["NFP+", "ENS+", "RN+"])].copy()
    data["rho"] = data["department_correlation"].map(
        lambda value: f"{value:g}".replace(".", ",")
    )
    data["lambda"] = data["mixing_weight"].map(
        lambda value: f"λ={value:g}".replace(".", ",")
    )
    data["reference"] = np.isclose(data["department_correlation"], 0.5) & np.isclose(
        data["mixing_weight"], 0.5
    )

    rho_order = ["0", "0,25", "0,5", "0,75", "1"]
    lambda_order = ["λ=1", "λ=0,75", "λ=0,5", "λ=0,25", "λ=0"]
    base = alt.Chart(data).encode(
        x=alt.X("rho:N", sort=rho_order, title="Intra-département ρ"),
        y=alt.Y("lambda:N", sort=lambda_order, title=None),
        tooltip=[
            alt.Tooltip("party:N", title="Groupe"),
            alt.Tooltip("department_correlation:Q", title="ρ"),
            alt.Tooltip("mixing_weight:Q", title="λ"),
            alt.Tooltip("width90:Q", title="Largeur à 90 %", format=".1f"),
        ],
    )
    heatmap_range = (
        ["#27313f", "#286ba3", "#63a8e8"] if dark else ["#edf4fb", "#75add8", "#075a9c"]
    )
    tiles = base.mark_rect(
        stroke="#343944" if dark else "#ffffff", strokeWidth=0.7
    ).encode(
        color=alt.Color(
            "width90:Q",
            title="Largeur de l'intervalle à 90 %",
            scale=alt.Scale(range=heatmap_range),
            legend=None,
        )
    )
    labels = base.mark_text(font="Arial", fontSize=10, fontWeight=600).encode(
        text=alt.Text("width90:Q", format=".0f"),
        color=alt.condition(
            f"datum.width90 >= {55 if dark else 78}",
            alt.value("white"),
            alt.value("#16181d"),
        ),
    )
    reference = base.transform_filter("datum.reference").mark_rect(
        fillOpacity=0, stroke="#e9eaee" if dark else "#16181d", strokeWidth=2.2
    )
    chart = (
        alt.layer(tiles, labels, reference)
        .properties(width=170, height=190)
        .facet(column=alt.Column("party:N", title=None, sort=["NFP+", "ENS+", "RN+"]))
        .properties(
            title=alt.Title(
                "Effet de la dépendance sur l'incertitude nationale",
                subtitle=[
                    "Largeur de l'intervalle central à 90 % des sièges pour chaque ρ et λ fixés.",
                    "Plus la case est foncée, plus l'intervalle est large ; le contour indique ρ=0,5 et λ=0,5.",
                ],
            )
        )
    )
    return _style(chart, dark=dark).resolve_scale(color="shared")


def seats_non_expressed_chart(*, dark: bool = False) -> alt.Chart:
    """Median seats conditional on simulated non-expressed vote share."""
    data = pd.read_csv(PRIOR_DIR / "seats-by-non-expressed.csv")
    stable = data[data["simulations"] >= 25].copy()
    if not stable.empty:
        data = stable
    data = data.rename(
        columns={"non_exprimés": "non_expressed", "sieges_medians": "median_seats"}
    )

    colours = {
        party_label(family): colour
        for family, colour in chart_palette(dark=dark).items()
    }
    parties = list(dict.fromkeys(data["parti"]))
    colour = alt.Color(
        "parti:N",
        legend=alt.Legend(
            title=None,
            orient="top",
            direction="horizontal",
            columns=len(parties),
        ),
        scale=alt.Scale(
            domain=parties,
            range=[colours.get(party, "#777777") for party in parties],
        ),
    )
    encoding = {
        "x": alt.X(
            "non_expressed:Q",
            title="Abstention + votes blancs/nuls (% des inscrits)",
            axis=alt.Axis(tickCount=12),
        ),
        "y": alt.Y(
            "median_seats:Q",
            title="Sièges médians",
            scale=alt.Scale(zero=True),
        ),
        "color": colour,
        "tooltip": [
            alt.Tooltip("parti:N", title="Groupe"),
            alt.Tooltip("non_expressed:Q", title="Non-exprimés", format=".1f"),
            alt.Tooltip("median_seats:Q", title="Sièges médians", format=".1f"),
            alt.Tooltip("simulations:Q", title="Simulations", format=",d"),
        ],
    }
    main_parties = ["NFP+", "ENS+", "RN+"]
    main_party = alt.FieldOneOfPredicate(field="parti", oneOf=main_parties)
    line = (
        alt.Chart(data)
        .mark_line()
        .encode(
            strokeWidth=alt.condition(main_party, alt.value(2.8), alt.value(1.2)),
            opacity=alt.condition(main_party, alt.value(1), alt.value(0.45)),
            **encoding,
        )
    )
    points = (
        alt.Chart(data)
        .mark_point(filled=True)
        .encode(
            size=alt.condition(main_party, alt.value(36), alt.value(18)),
            opacity=alt.condition(main_party, alt.value(1), alt.value(0.45)),
            **encoding,
        )
    )
    chart = (line + points).properties(
        width=680,
        height=318,
        title=alt.Title(
            "Sièges selon la part simulée de non-exprimés",
            subtitle=(
                "Distribution prédictive a priori du modèle national ancré, α=1 ; "
                "chaque point agrège un point de pourcentage."
            ),
        ),
    )
    return _style(chart, dark=dark)


def alpha_sensitivity_chart(*, dark: bool = False) -> alt.Chart:
    """Prior-predictive seat intervals for fixed Dirichlet concentrations."""
    data = pd.read_csv(PRIOR_DIR / "alpha-sensitivity.csv")
    data["alpha_label"] = data["alpha"].map(
        lambda value: f"α={value:g}".replace(".", ",")
    )

    parties = list(dict.fromkeys(data["parti"]))
    alpha_order = [
        f"α={value:g}".replace(".", ",") for value in sorted(data["alpha"].unique())
    ]
    colours = {
        party_label(family): colour
        for family, colour in chart_palette(dark=dark).items()
    }
    colour = alt.Color(
        "parti:N",
        legend=None,
        scale=alt.Scale(
            domain=parties,
            range=[colours.get(party, "#777777") for party in parties],
        ),
    )
    shared = {
        "y": alt.Y(
            "parti:N",
            sort=parties,
            title=None,
            axis=alt.Axis(grid=True, ticks=False),
        ),
        "yOffset": alt.YOffset("alpha_label:N", sort=alpha_order),
        "color": colour,
        "tooltip": [
            alt.Tooltip("parti:N", title="Groupe"),
            alt.Tooltip("alpha:Q", title="α"),
            alt.Tooltip("p05:Q", title="5%", format=".0f"),
            alt.Tooltip("mediane:Q", title="Médiane", format=".0f"),
            alt.Tooltip("p95:Q", title="95%", format=".0f"),
        ],
    }
    x_scale = alt.Scale(domain=[0, max(270, float(data["p95"].max()) + 15)])
    intervals = (
        alt.Chart(data)
        .mark_rule(strokeWidth=2)
        .encode(
            x=alt.X("p05:Q", title="Sièges", scale=x_scale),
            x2="p95:Q",
            **shared,
        )
    )
    medians = (
        alt.Chart(data)
        .mark_point(filled=True, size=42)
        .encode(x=alt.X("mediane:Q", scale=x_scale), **shared)
    )
    labels = (
        alt.Chart(data)
        .mark_text(
            align="left",
            baseline="middle",
            dx=5,
            color="#aeb4c0" if dark else "#5a616e",
            font="Arial",
            fontSize=9,
        )
        .encode(
            x=alt.X("p95:Q", scale=x_scale),
            y=shared["y"],
            yOffset=shared["yOffset"],
            text="alpha_label:N",
        )
    )
    chart = alt.layer(intervals, medians, labels).properties(
        width=650,
        height=46 * len(parties),
        title=alt.Title(
            "Sensibilité à la concentration de la loi de Dirichlet",
            subtitle=(
                "Médiane et intervalle prédictif a priori à 90 % ; "
                "aucun résultat du second tour n'est utilisé."
            ),
        ),
    )
    return _style(chart, dark=dark)


def demobilisation_sensitivity_chart(*, dark: bool = False) -> alt.Chart:
    """Seat intervals when the national qualified-voter demobilisation is fixed."""
    data = pd.read_csv(PRIOR_DIR / "demobilisation-sensitivity.csv")
    rates = sorted(data["demobilisation"].unique())
    rate_order = [f"{rate:.0%}" for rate in rates]
    data["d_label"] = data["demobilisation"].map(lambda value: f"{value:.0%}")
    parties = list(dict.fromkeys(data["parti"]))
    colours = {
        party_label(family): colour
        for family, colour in chart_palette(dark=dark).items()
    }

    shared = {
        "y": alt.Y(
            "d_label:N",
            sort=rate_order,
            title="d fixé",
            axis=alt.Axis(ticks=False, grid=False),
        ),
        "color": alt.Color(
            "parti:N",
            legend=None,
            scale=alt.Scale(
                domain=parties,
                range=[colours.get(party, "#777777") for party in parties],
            ),
        ),
        "tooltip": [
            alt.Tooltip("parti:N", title="Groupe"),
            alt.Tooltip("demobilisation:Q", title="d fixé", format=".0%"),
            alt.Tooltip("p05:Q", title="5%", format=".0f"),
            alt.Tooltip("mediane:Q", title="Médiane", format=".0f"),
            alt.Tooltip("p95:Q", title="95%", format=".0f"),
        ],
    }
    intervals = (
        alt.Chart(data)
        .mark_rule(strokeWidth=3, strokeCap="round", opacity=0.7)
        .encode(
            x=alt.X("p05:Q", title="Sièges", scale=alt.Scale(zero=False)),
            x2="p95:Q",
            **shared,
        )
    )
    medians = (
        alt.Chart(data)
        .mark_point(filled=True, size=42)
        .encode(
            x=alt.X("mediane:Q", scale=alt.Scale(zero=False)),
            **shared,
        )
    )
    chart = (
        alt.layer(intervals, medians)
        .properties(width=180, height=125)
        .facet(
            facet=alt.Facet("parti:N", sort=parties, title=None),
            columns=3,
            title=alt.Title(
                "Sensibilité à la démobilisation des électeurs qualifiés",
                subtitle=(
                    "Modèle national ancré ; médiane et intervalle prédictif a priori "
                    "central à 90 % pour chaque valeur de d."
                ),
            ),
        )
        .resolve_scale(x="independent")
    )
    return _style(chart, dark=dark)


def seat_results_chart(*, dark: bool = False) -> alt.Chart:
    """Marginal seat intervals, naïve baseline and observed result."""
    model_labels = {
        "national": "National",
        "national_anchored": "National ancré",
        "kernel_anchored": "Local ancré",
    }
    data = pd.concat(
        [
            pd.read_csv(RESULTS_DIR / f"seat-intervals-{model}.csv")
            for model in model_labels
        ],
        ignore_index=True,
    )
    data["model_label"] = data["model"].map(model_labels)
    reference_label = "Référence naïve"
    reference_data = pd.read_csv(RESULTS_DIR / "baseline-first-round-leader.csv")
    reference_data["model_label"] = reference_label

    parties = ["NFP+", "DVG", "ENS+", "LR", "DVD", "RN+", "DIV"]
    models = [*model_labels.values(), reference_label]
    colours = (
        ["#35a98d", "#4c96ee", "#d58a45", "#aeb4c0"]
        if dark
        else ["#1f8a70", "#2a78d6", "#b56824", "#5a616e"]
    )
    colour = alt.Color(
        "model_label:N",
        title=None,
        sort=models,
        scale=alt.Scale(domain=models, range=colours),
        legend=alt.Legend(orient="top", direction="horizontal"),
    )
    shape = alt.Shape(
        "model_label:N",
        title=None,
        sort=models,
        scale=alt.Scale(
            domain=models,
            range=["circle", "circle", "circle", "cross"],
        ),
        legend=alt.Legend(orient="top", direction="horizontal"),
    )
    shared = {
        "y": alt.Y(
            "party:N",
            sort=parties,
            title=None,
            axis=alt.Axis(grid=True, ticks=False),
        ),
        "yOffset": alt.YOffset("model_label:N", sort=models),
        "color": colour,
        "tooltip": [
            alt.Tooltip("party:N", title="Groupe"),
            alt.Tooltip("model_label:N", title="Modèle"),
            alt.Tooltip("p05:Q", title="5%", format=".0f"),
            alt.Tooltip("p25:Q", title="25%", format=".0f"),
            alt.Tooltip("median:Q", title="Médiane", format=".0f"),
            alt.Tooltip("p75:Q", title="75%", format=".0f"),
            alt.Tooltip("p95:Q", title="95%", format=".0f"),
            alt.Tooltip("actual:Q", title="Résultat réel", format=".0f"),
        ],
    }
    seat_scale = alt.Scale(domain=[0, 320])
    x = alt.X("p05:Q", title="Sièges", scale=seat_scale)
    interval_90 = (
        alt.Chart(data)
        .mark_rule(strokeWidth=3, opacity=0.78, strokeCap="round")
        .encode(x=x, x2="p95:Q", **shared)
    )
    interval_50 = (
        alt.Chart(data)
        .mark_rule(strokeWidth=9, opacity=0.92, strokeCap="round")
        .encode(x=alt.X("p25:Q", scale=seat_scale), x2="p75:Q", **shared)
    )
    medians = (
        alt.Chart(data)
        .mark_point(
            filled=True,
            size=55,
            stroke="#14161a" if dark else "#fbfbfc",
            strokeWidth=1,
        )
        .encode(x=alt.X("median:Q", scale=seat_scale), shape=shape, **shared)
    )
    reference = (
        alt.Chart(reference_data)
        .mark_point(
            filled=False,
            size=82,
            strokeWidth=2,
        )
        .encode(
            x=alt.X("baseline_seats:Q", scale=seat_scale),
            y=shared["y"],
            yOffset=alt.YOffset("model_label:N", sort=models),
            color=colour,
            shape=shape,
            tooltip=[
                alt.Tooltip("party:N", title="Groupe"),
                alt.Tooltip("model_label:N", title="Modèle"),
                alt.Tooltip(
                    "baseline_seats:Q", title="Sièges de référence", format=".0f"
                ),
            ],
        )
    )
    actual_data = data[["party", "actual"]].drop_duplicates()
    actual_tooltip = [
        alt.Tooltip("party:N", title="Groupe"),
        alt.Tooltip("actual:Q", title="Résultat réel", format=".0f"),
    ]
    actual_guides = (
        alt.Chart(actual_data)
        .mark_tick(
            orient="vertical",
            size=58,
            thickness=1.3,
            strokeDash=[4, 3],
            color="#e9eaee" if dark else "#16181d",
            opacity=0.72,
        )
        .encode(
            x=alt.X("actual:Q", scale=seat_scale),
            y=shared["y"],
            tooltip=actual_tooltip,
        )
    )
    actuals = (
        alt.Chart(actual_data)
        .mark_point(
            shape="diamond",
            filled=True,
            size=72,
            color="#e9eaee" if dark else "#16181d",
            stroke="#14161a" if dark else "#fbfbfc",
            strokeWidth=1,
        )
        .encode(
            x=alt.X("actual:Q", scale=seat_scale),
            y=shared["y"],
            tooltip=actual_tooltip,
        )
    )
    actual_labels = (
        alt.Chart(actual_data)
        .mark_text(
            align="center",
            baseline="bottom",
            dy=-11,
            color="#e9eaee" if dark else "#16181d",
            font="Arial",
            fontSize=10,
            fontWeight=600,
        )
        .encode(
            x=alt.X("actual:Q", scale=seat_scale),
            y=shared["y"],
            text=alt.Text("actual:Q", format=".0f"),
        )
    )
    chart = alt.layer(
        interval_90,
        interval_50,
        medians,
        reference,
        actual_guides,
        actuals,
        actual_labels,
    ).properties(width=650, height=76 * len(parties))
    return _style(chart, dark=dark)


def conditioned_seat_results_chart(*, dark: bool = False) -> alt.Chart:
    """Kernel-model seat intervals before and after observing expressed share."""
    data = pd.read_csv(RESULTS_DIR / "seat-intervals-conditioned-on-expressed.csv")
    data = data[data["model"].eq("kernel_anchored")]
    parties = ["NFP+", "DVG", "ENS+", "LR", "DVD", "RN+", "DIV"]
    condition_labels = {
        "Prior predictive": "Prédictive a priori",
        "Observed expressed share": "Part exprimée observée",
    }
    data["conditioning"] = data["conditioning"].replace(condition_labels)
    conditions = list(condition_labels.values())
    colours = ["#5795df", "#d68a45"] if dark else ["#2a78d6", "#b56824"]
    colour = alt.Color(
        "conditioning:N",
        title=None,
        sort=conditions,
        scale=alt.Scale(domain=conditions, range=colours),
        legend=alt.Legend(orient="top", direction="horizontal"),
    )
    shared = {
        "y": alt.Y(
            "party:N",
            sort=parties,
            title=None,
            axis=alt.Axis(grid=True, ticks=False),
        ),
        "yOffset": alt.YOffset("conditioning:N", sort=conditions),
        "color": colour,
        "tooltip": [
            alt.Tooltip("party:N", title="Groupe"),
            alt.Tooltip("conditioning:N", title="Distribution"),
            alt.Tooltip("p05:Q", title="5%", format=".0f"),
            alt.Tooltip("p25:Q", title="25%", format=".0f"),
            alt.Tooltip("median:Q", title="Médiane", format=".0f"),
            alt.Tooltip("p75:Q", title="75%", format=".0f"),
            alt.Tooltip("p95:Q", title="95%", format=".0f"),
            alt.Tooltip("actual:Q", title="Résultat réel", format=".0f"),
        ],
    }
    scale = alt.Scale(domain=[0, 260])
    intervals_90 = (
        alt.Chart(data)
        .mark_rule(strokeWidth=3, opacity=0.78, strokeCap="round")
        .encode(x=alt.X("p05:Q", title="Sièges", scale=scale), x2="p95:Q", **shared)
    )
    intervals_50 = (
        alt.Chart(data)
        .mark_rule(strokeWidth=9, opacity=0.92, strokeCap="round")
        .encode(x=alt.X("p25:Q", scale=scale), x2="p75:Q", **shared)
    )
    medians = (
        alt.Chart(data)
        .mark_point(
            filled=True,
            size=55,
            stroke="#14161a" if dark else "#fbfbfc",
            strokeWidth=1,
        )
        .encode(x=alt.X("median:Q", scale=scale), **shared)
    )
    actual_data = data[["party", "actual"]].drop_duplicates()
    actuals = (
        alt.Chart(actual_data)
        .mark_point(
            shape="diamond",
            filled=True,
            size=70,
            color="#e9eaee" if dark else "#16181d",
            stroke="#14161a" if dark else "#fbfbfc",
            strokeWidth=1,
        )
        .encode(
            x=alt.X("actual:Q", scale=scale),
            y=shared["y"],
            tooltip=[
                alt.Tooltip("party:N", title="Groupe"),
                alt.Tooltip("actual:Q", title="Résultat réel", format=".0f"),
            ],
        )
    )
    selected = int(data["selected_draws"].iloc[0])
    total = int(data["total_draws"].iloc[0])
    target = float(data["target_expressed_share"].iloc[0])
    window = float(data["window_points"].iloc[0])
    selected_label = f"{selected:,}".replace(",", "\u202f")
    total_label = f"{total:,}".replace(",", "\u202f")
    target_label = f"{target:.2f}".replace(".", ",")
    window_label = f"{window:g}".replace(".", ",")
    chart = alt.layer(intervals_90, intervals_50, medians, actuals).properties(
        width=650,
        height=58 * len(parties),
        title=alt.Title(
            "Intervalles de sièges conditionnés par la part exprimée observée",
            subtitle=(
                f"Modèle local ancré ; {selected_label}/{total_label} tirages à ±{window_label} "
                f"point de la valeur observée ({target_label} %)."
            ),
        ),
    )
    return _style(chart, dark=dark)


def joint_region_chart(*, dark: bool = False) -> alt.Chart:
    """Position of the observed seat vector in both joint predictive laws."""
    models = {
        "national_anchored": "National ancré",
        "kernel_anchored": "Local ancré",
    }
    panels = []
    ink = "#e9eaee" if dark else "#16181d"
    for model, label in models.items():
        data = pd.read_csv(RESULTS_DIR / f"joint-diagnostics-{model}.csv")
        scores = data[data["role"].eq("calibration")][["joint_score"]]
        observed = data[data["role"].eq("observed")].iloc[0]
        q50, q90 = scores["joint_score"].quantile([0.5, 0.9], interpolation="higher")
        colour = MODEL_COLOURS[label]

        histogram = (
            alt.Chart(scores)
            .mark_bar(color=colour, opacity=0.58)
            .encode(
                x=alt.X(
                    "joint_score:Q",
                    bin=alt.Bin(maxbins=28),
                    title="Score énergétique joint",
                ),
                y=alt.Y("count():Q", title="Simulations"),
                tooltip=[
                    alt.Tooltip(
                        "joint_score:Q",
                        bin=alt.Bin(maxbins=28),
                        title="Score",
                        format=".1f",
                    ),
                    alt.Tooltip("count():Q", title="Simulations"),
                ],
            )
        )
        thresholds = pd.DataFrame({"score": [q50, q90], "label": ["50%", "90%"]})
        threshold_rules = (
            alt.Chart(thresholds)
            .mark_rule(color=colour, strokeWidth=1.4, strokeDash=[3, 2])
            .encode(x="score:Q")
        )
        threshold_labels = (
            alt.Chart(thresholds)
            .mark_text(
                align="center",
                baseline="bottom",
                dy=-3,
                color=colour,
                font="Arial",
                fontSize=9,
            )
            .encode(x="score:Q", y=alt.value(108), text="label:N")
        )
        percentile = float(observed["observed_percentile"])
        observed_data = pd.DataFrame({"score": [float(observed["joint_score"])]})
        observed_rule = (
            alt.Chart(observed_data)
            .mark_rule(color=ink, strokeWidth=1.5)
            .encode(x="score:Q")
        )
        panels.append(
            alt.layer(
                histogram,
                threshold_rules,
                threshold_labels,
                observed_rule,
            ).properties(
                width=650,
                height=112,
                title=alt.Title(
                    f"{label} · résultat réel au percentile {percentile:.0%}",
                    anchor="start",
                    fontSize=11,
                ),
            )
        )

    chart = alt.vconcat(*panels, spacing=18).properties(
        title=alt.Title(
            "Où se situe conjointement le résultat réel ?",
            subtitle=(
                "Centralité fondée sur le score énergétique et un échantillon scindé ; "
                "un score faible est plus central dans le modèle."
            ),
        )
    )
    return _style(chart, dark=dark).resolve_scale(x="independent", y="independent")


def _dominant_party_data() -> pd.DataFrame:
    labels = {
        "national_anchored": "National ancré",
        "kernel_anchored": "Local ancré",
    }
    seat_columns = ["NFP+", "DVG", "ENS+", "LR", "DVD", "RN+", "DIV"]
    rows = []
    for model, model_label in labels.items():
        data = pd.read_csv(RESULTS_DIR / f"joint-diagnostics-{model}.csv")
        sample = data[~data["role"].eq("observed")]
        values = sample[seat_columns].to_numpy()
        maxima = values.max(axis=1)
        tied = (values == maxima[:, None]).sum(axis=1) > 1
        winners = np.asarray(seat_columns, dtype=object)[values.argmax(axis=1)]
        winners[tied] = TIE_LABEL
        for party in ["NFP+", "ENS+", "RN+", TIE_LABEL]:
            rows.append(
                {
                    "model": model_label,
                    "party": party,
                    "probability": float(np.mean(winners == party)),
                }
            )
    return pd.DataFrame(rows)


TIE_LABEL = "Égalité en tête"
TIE_COLOUR_LIGHT, TIE_COLOUR_DARK = "#8a9099", "#8f97a5"


def dominant_party_chart(*, dark: bool = False) -> alt.Chart:
    """
    Probabilité d'être seul premier groupe, pour le seul modèle retenu.

    Une seule série : des barres horizontales suffisent, et la couleur peut donc
    servir à identifier le GROUPE plutôt qu'un modèle. C'est la lecture utile
    ici — on compare des partis entre eux, pas des variantes du modèle — et elle
    réutilise les teintes employées partout ailleurs dans le billet. L'égalité,
    qui n'est pas un parti, garde le gris neutre des non-exprimés.
    """
    colours = {
        party_label(family): hex for family, hex in chart_palette(dark=dark).items()
    }
    colours[TIE_LABEL] = TIE_COLOUR_DARK if dark else TIE_COLOUR_LIGHT

    data = _dominant_party_data()
    data = data[data["model"] == "National ancré"]
    order = data.sort_values("probability", ascending=False)["party"].tolist()

    base = alt.Chart(data).encode(
        x=alt.X(
            "probability:Q",
            title="Probabilité d'être l'unique premier groupe",
            axis=alt.Axis(format="%"),
            # Domaine dérivé : un maximum écrit en dur tronque la barre dès que
            # les artefacts changent, ce qui est arrivé.
            scale=alt.Scale(
                domain=[0, min(1.0, float(data["probability"].max()) * 1.22)]
            ),
        ),
        y=alt.Y("party:N", sort=order, title=None),
        tooltip=[
            alt.Tooltip("party:N", title="Groupe"),
            alt.Tooltip("probability:Q", title="Probabilité", format=".1%"),
        ],
    )
    bars = base.mark_bar(height=18, cornerRadiusEnd=3).encode(
        color=alt.Color(
            "party:N",
            scale=alt.Scale(domain=list(colours), range=list(colours.values())),
            legend=None,
        )
    )
    labels = base.mark_text(
        align="left",
        baseline="middle",
        dx=6,
        color="#e9eaee" if dark else "#16181d",
        font="Arial",
        fontWeight=600,
        fontSize=11,
    ).encode(text=alt.Text("probability:Q", format=".1%"))

    chart = (bars + labels).properties(
        width=560,
        height=alt.Step(30),
        title=alt.Title(
            "Qui obtient le plus de sièges ?",
            subtitle=(
                "Distribution prédictive a priori de la probabilité d'avoir une majorité relative"
            ),
        ),
    )
    return _style(chart, dark=dark)


def joint_seats_chart(*, dark: bool = False) -> alt.Chart:
    """Pairwise density projections of the main three seat totals."""
    data = pd.read_csv(RESULTS_DIR / "joint-diagnostics-kernel_anchored.csv")
    sample = data[~data["role"].eq("observed")]
    observed = data[data["role"].eq("observed")].iloc[0]
    pairs = [("NFP+", "ENS+"), ("NFP+", "RN+"), ("ENS+", "RN+")]
    panels = []

    for x_name, y_name in pairs:
        x_values = sample[x_name].to_numpy()
        y_values = sample[y_name].to_numpy()
        x_low, x_high = np.quantile(x_values, [0.005, 0.995])
        y_low, y_high = np.quantile(y_values, [0.005, 0.995])
        x_low, x_high = 10 * np.floor(x_low / 10), 10 * np.ceil(x_high / 10)
        y_low, y_high = 10 * np.floor(y_low / 10), 10 * np.ceil(y_high / 10)
        counts, x_edges, y_edges = np.histogram2d(
            x_values,
            y_values,
            bins=12,
            range=[[x_low, x_high], [y_low, y_high]],
        )
        bins = pd.DataFrame(
            [
                {
                    "x0": x_edges[ix],
                    "x1": x_edges[ix + 1],
                    "y0": y_edges[iy],
                    "y1": y_edges[iy + 1],
                    "count": counts[ix, iy],
                }
                for ix, iy in np.argwhere(counts > 0)
            ]
        )
        density = (
            alt.Chart(bins)
            .mark_rect()
            .encode(
                x=alt.X(
                    "x0:Q",
                    title=f"Sièges {x_name}",
                    scale=alt.Scale(domain=[x_low, x_high]),
                ),
                x2="x1:Q",
                y=alt.Y(
                    "y0:Q",
                    title=f"Sièges {y_name}",
                    scale=alt.Scale(domain=[y_low, y_high]),
                ),
                y2="y1:Q",
                color=alt.Color(
                    "count:Q",
                    scale=alt.Scale(
                        range=(
                            ["#27313f", "#286ba3", "#63a8e8"]
                            if dark
                            else ["#edf4fb", "#75add8", "#075a9c"]
                        )
                    ),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("x0:Q", title=f"{x_name} : de", format=".0f"),
                    alt.Tooltip("x1:Q", title="à", format=".0f"),
                    alt.Tooltip("y0:Q", title=f"{y_name} : de", format=".0f"),
                    alt.Tooltip("y1:Q", title="à", format=".0f"),
                    alt.Tooltip("count:Q", title="Simulations", format=".0f"),
                ],
            )
        )
        actual = (
            alt.Chart(
                pd.DataFrame(
                    {
                        "x": [observed[x_name]],
                        "y": [observed[y_name]],
                        "label": ["Résultat réel de 2024"],
                    }
                )
            )
            .mark_point(
                shape="diamond",
                filled=True,
                size=95,
                color="#e9eaee" if dark else "#16181d",
                stroke="#14161a" if dark else "white",
                strokeWidth=1,
            )
            .encode(x="x:Q", y="y:Q", tooltip=alt.Tooltip("label:N", title=None))
        )
        panels.append((density + actual).properties(width=174, height=174))

    chart = alt.hconcat(*panels, spacing=25).properties(
        title=alt.Title(
            "Corrélation des prédictions de sièges",
            subtitle="Distribution prédictive a priori du modèle local ancré ; les cases foncées contiennent davantage de simulations et le losange indique le résultat réel.",
        )
    )
    return _style(chart, dark=dark).resolve_scale(color="independent")


def expressed_share_chart(*, dark: bool = False) -> alt.Chart:
    """Prior-predictive national expressed share under the anchored model."""
    data = pd.read_csv(RESULTS_DIR / "expressed-diagnostics-national_anchored.csv")
    data = data[data["scope"].eq("national_draw")]
    n_simulations = len(data)
    n_simulations_label = f"{n_simulations:,}".replace(",", "\u202f")
    median = float(data["predicted_share"].median())
    low, high = data["predicted_share"].quantile([0.05, 0.95])
    v_low, v_high = data["predicted_share"].quantile([0.005, 0.995])
    interval = pd.DataFrame({"low": [low], "high": [high], "median": [median]})

    histogram = (
        alt.Chart(data)
        .mark_bar(color="#2a78d6", opacity=0.78)
        .encode(
            x=alt.X(
                "predicted_share:Q",
                bin=alt.Bin(maxbins=32),
                title="Part nationale de suffrages exprimés (% des inscrits)",
                scale=alt.Scale(domain=[v_low, v_high]),
            ),
            y=alt.Y("count():Q", title="Nombre de simulations"),
            tooltip=[
                alt.Tooltip(
                    "predicted_share:Q",
                    bin=alt.Bin(maxbins=32),
                    title="Part exprimée",
                    format=".1f",
                ),
                alt.Tooltip("count():Q", title="Simulations"),
            ],
        )
    )
    band = (
        alt.Chart(interval)
        .mark_rect(color="#b56824", opacity=0.16)
        .encode(x="low:Q", x2="high:Q")
    )
    median_rule = (
        alt.Chart(interval)
        .mark_rule(color="#b56824", strokeWidth=2)
        .encode(x="median:Q")
    )
    chart = (band + histogram + median_rule).properties(
        width=620,
        height=225,
        title=alt.Title(
            "Distribution prédictive des suffrages exprimés",
            subtitle=(
                f"Modèle national ancré, {n_simulations_label} simulations ; bande orange : intervalle central à 90 %, "
                "trait : médiane."
            ),
        ),
    )
    return _style(chart, dark=dark)


def district_0101_national_delta_chart(*, dark: bool = False) -> alt.Chart:
    """Distribution de la cible exprimée de 0101 due au seul choc national."""
    districts = load_full_results().districts
    shares_and_weights = []
    district_share = None
    for district in districts:
        expressed = sum(district.competing_parties_results.values()) + sum(
            district.eliminated_parties_results.values()
        )
        registered = expressed + district.non_expressed
        share = expressed / registered
        shares_and_weights.append((share, registered))
        if district.circonscription.id == "0101":
            district_share = share
    if district_share is None:
        raise ValueError("La circonscription 0101 est absente des données.")

    shares = np.array([share for share, _ in shares_and_weights])
    weights = np.array([weight for _, weight in shares_and_weights])
    national_share = float(weights @ shares / weights.sum())
    centre = national_share + DEFAULT_EXPECTED_EXPRESSED_CHANGE_PTS / 100
    mean_delta = float(logit(centre) - logit(national_share))

    # Même conversion que le modèle ancré : la bande déclarée est une
    # demi-largeur centrale à 90 % sur l'échelle des pourcentages.
    anchor_logit = logit(centre)
    points = DEFAULT_NATIONAL_EXPRESSED_BAND_PTS / 100
    sigma = min(
        abs(logit(centre - points) - anchor_logit),
        abs(logit(centre + points) - anchor_logit),
    ) / norm.ppf(0.95)

    rng = np.random.default_rng(DEFAULT_SEED)
    delta = rng.normal(mean_delta, sigma, DELTA_EXAMPLE_DRAWS)
    targets = 100 * expit(logit(district_share) + delta)
    low, median, high = np.quantile(targets, [0.05, 0.5, 0.95])
    q005, q995 = np.quantile(targets, [0.005, 0.995])
    span = max(median - q005, q995 - median)
    domain = [median - span, median + span]
    # Les 0,5 % de chaque queue rendent l'axe peu lisible alors qu'ils sont
    # pratiquement invisibles dans l'histogramme.
    shown = targets[(targets >= domain[0]) & (targets <= domain[1])]
    data = pd.DataFrame({"target": shown})
    bounds = pd.DataFrame({"low": [low], "median": [median], "high": [high]})

    bars = (
        alt.Chart(data)
        .mark_bar(color="#2a78d6", opacity=0.8)
        .encode(
            x=alt.X(
                "target:Q",
                bin=alt.Bin(maxbins=34),
                title="Cible de suffrages exprimés en 0101 (% des inscrits)",
                scale=alt.Scale(domain=domain, nice=False),
            ),
            y=alt.Y("count():Q", title="Nombre de tirages"),
            tooltip=[
                alt.Tooltip(
                    "target:Q", bin=alt.Bin(maxbins=34), title="Cible", format=".1f"
                ),
                alt.Tooltip("count():Q", title="Tirages"),
            ],
        )
    )
    band = (
        alt.Chart(bounds)
        .mark_rect(color="#b56824", opacity=0.16)
        .encode(x="low:Q", x2="high:Q")
    )
    median_rule = (
        alt.Chart(bounds).mark_rule(color="#b56824", strokeWidth=2).encode(x="median:Q")
    )
    draw_count_label = f"{len(delta):,}".replace(",", "\u202f")
    chart = (band + bars + median_rule).properties(
        width=620,
        height=225,
        title=alt.Title(
            "0101 : incertitude sur le choc national",
            subtitle=(
                f"Partie centrale à 99 % des {draw_count_label} tirages de δnat, avec δ0101 = 0 ; "
                "bande orange : intervalle à 90 %, trait : médiane."
            ),
        ),
    )
    return _style(chart, dark=dark)


def district_expressed_error_chart(*, dark: bool = False) -> alt.Chart:
    """Distribution of district median errors in expressed-vote share."""
    labels = {
        "national": "National",
        "national_anchored": "National ancré",
        "kernel_anchored": "Local ancré",
    }
    frames = []
    for model, label in labels.items():
        frame = pd.read_csv(RESULTS_DIR / f"expressed-diagnostics-{model}.csv")
        frame = frame[frame["scope"].eq("district")].copy()
        frame["model_label"] = label
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    data["error"] = data["error"].abs()
    domain = list(labels.values())
    colours = ["#7b818c", "#2a78d6", "#b56824"]
    base = alt.Chart(data).encode(
        x=alt.X(
            "error:Q",
            bin=alt.Bin(step=2),
            title=None,
            axis=alt.Axis(values=[0, 4, 8, 12, 16, 20]),
        ),
        y=alt.Y("count():Q", title="Circonscriptions"),
        color=alt.Color(
            "model_label:N",
            scale=alt.Scale(domain=domain, range=colours),
            legend=None,
        ),
        tooltip=[
            alt.Tooltip("error:Q", bin=alt.Bin(step=1), title="Erreur", format=".0f"),
            alt.Tooltip("count():Q", title="Circonscriptions"),
        ],
    )
    bars = base.mark_bar(opacity=0.82)
    zero = base.mark_rule(
        color="#e9eaee" if dark else "#16181d", strokeWidth=1.2
    ).encode(x=alt.datum(0))
    chart = (
        alt.layer(bars, zero)
        .properties(width=185, height=155)
        .facet(column=alt.Column("model_label:N", sort=domain, title=None))
        .properties(
            title=alt.Title(
                "Écart aux suffrages exprimés réellement observés",
                subtitle=(
                    "Erreur absolue entre la médiane prédictive et le résultat réel, "
                    "en points de pourcentage."
                ),
            )
        )
    )
    return _style(chart, dark=dark)


def simplex_chart(*, dark: bool = False) -> alt.Chart:
    """Theoretical ordered two-way split for three Dirichlet concentrations."""
    grid = np.linspace(0.002, 0.5, 400)
    rows = []
    for alpha in DIRICHLET_SPLIT_ALPHAS:
        density = 2 * beta.pdf(grid, alpha, alpha)
        for rate, value in zip(grid, density, strict=True):
            rows.append(
                {
                    "alpha": alpha,
                    "alpha_label": f"α = {alpha:g}".replace(".", ","),
                    "transfer": "ENS+ → RN+",
                    "rate": rate,
                    "density": value,
                }
            )
            rows.append(
                {
                    "alpha": alpha,
                    "alpha_label": f"α = {alpha:g}".replace(".", ","),
                    "transfer": "ENS+ → LR",
                    "rate": 1 - rate,
                    "density": value,
                }
            )

    transfers = ["ENS+ → LR", "ENS+ → RN+"]
    if dark:
        colours = ["#39a0ff", "#79aee3"]
    else:
        palette = chart_palette(dark=False)
        colours = [palette["LR"], palette["RN+"]]
    base = (
        alt.Chart(pd.DataFrame(rows))
        .mark_line(strokeWidth=2.5)
        .encode(
            x=alt.X(
                "rate:Q",
                title="Taux de report",
                scale=alt.Scale(domain=[0, 1], nice=False),
                axis=alt.Axis(values=[0, 0.25, 0.5, 0.75, 1], format=".0%"),
            ),
            y=alt.Y("density:Q", title="Densité", scale=alt.Scale(zero=True)),
            color=alt.Color(
                "transfer:N",
                sort=transfers,
                scale=alt.Scale(domain=transfers, range=colours),
                legend=alt.Legend(orient="top", direction="horizontal"),
            ),
            tooltip=[
                alt.Tooltip("alpha:Q", title="α"),
                alt.Tooltip("transfer:N", title="Report"),
                alt.Tooltip("rate:Q", title="Taux", format=".1%"),
                alt.Tooltip("density:Q", title="Densité", format=".2f"),
            ],
        )
        .properties(width=200, height=180)
    )
    chart = base.facet(
        column=alt.Column(
            "alpha_label:N",
            sort=[
                f"α = {alpha:g}".replace(".", ",") for alpha in DIRICHLET_SPLIT_ALPHAS
            ],
            title=None,
            header=alt.Header(labelFontWeight=600),
        ),
        spacing=18,
        title=alt.TitleParams(
            "Distributions théoriques des reports entre deux destinations",
            subtitle=(
                "La plus grande part Gamma normalisée est attribuée à LR ; "
                "la plus petite à RN+."
            ),
        ),
    ).resolve_scale(y="independent")
    return _style(chart, dark=dark)


def tilt_effect_chart(*, dark: bool = False) -> alt.Chart:
    """Allocation of mobilised non-expressed voters for two duel balances."""
    scenarios = [
        ("Premier tour serré · A 55 % / B 45 %", 0.55),
        ("Premier tour déséquilibré · A 70 % / B 30 %", 0.70),
    ]
    rows = []
    for scenario, first_round_a in scenarios:
        first_round = np.array([first_round_a, 1 - first_round_a])
        for tilt in TILT_EXAMPLE_VALUES:
            shares = first_round**tilt
            shares /= shares.sum()
            start = 0.0
            for candidate, share in zip(("Candidat A", "Candidat B"), shares):
                end = start + float(share)
                rows.append(
                    {
                        "scenario": scenario,
                        "tilt": tilt,
                        "tilt_label": f"τ = {tilt:g}",
                        "band": "Flux mobilisé",
                        "candidate": candidate,
                        "share": float(share),
                        "start": start,
                        "end": end,
                        "middle": (start + end) / 2,
                        "share_label": f"{share:.0%}",
                    }
                )
                start = end

    data = pd.DataFrame(rows)
    candidates = ["Candidat A", "Candidat B"]
    colours = ["#4f83cc", "#d17b35"]
    shared = {
        "y": alt.Y("band:N", axis=None),
        "color": alt.Color(
            "candidate:N",
            sort=candidates,
            scale=alt.Scale(domain=candidates, range=colours),
            legend=alt.Legend(orient="top", direction="horizontal"),
        ),
        "tooltip": [
            alt.Tooltip("scenario:N", title="Premier tour"),
            alt.Tooltip("tilt:Q", title="Paramètre de tilt"),
            alt.Tooltip("candidate:N", title="Destination"),
            alt.Tooltip("share:Q", title="Flux mobilisé", format=".1%"),
        ],
    }
    bars = (
        alt.Chart(data)
        .mark_bar(size=24)
        .encode(
            x=alt.X(
                "start:Q",
                title="Part du flux mobilisé",
                scale=alt.Scale(domain=[0, 1], nice=False),
                axis=alt.Axis(values=[0, 0.5, 1], format=".0%"),
            ),
            x2="end:Q",
            **shared,
        )
    )
    labels = (
        alt.Chart(data)
        .mark_text(
            color="white",
            font="Arial",
            fontSize=11,
            fontWeight=600,
        )
        .encode(
            x=alt.X("middle:Q", scale=alt.Scale(domain=[0, 1], nice=False)),
            y=alt.Y("band:N", axis=None),
            text="share_label:N",
            detail="candidate:N",
        )
    )
    chart = (
        (bars + labels)
        .properties(width=176, height=34)
        .facet(
            row=alt.Row(
                "scenario:N",
                sort=[scenario for scenario, _ in scenarios],
                title=None,
                header=alt.Header(labelAngle=0, labelAlign="left", labelFontWeight=600),
            ),
            column=alt.Column(
                "tilt_label:N",
                sort=[f"τ = {tilt:g}" for tilt in TILT_EXAMPLE_VALUES],
                title=None,
                header=alt.Header(labelFontWeight=600),
            ),
            spacing=16,
            title=alt.TitleParams(
                "Effet du tilt sur la répartition des électeurs mobilisés dans un duel",
                subtitle="Lignes : rapport de force au premier tour · colonnes : tilt national",
            ),
        )
    )
    return _style(chart, dark=dark)


def win_probability_calibration_chart(
    *, model: str = "kernel_anchored", dark: bool = False
) -> alt.Chart:
    """Courbe de fiabilité : probabilité de victoire prédite contre fréquence
    réalisée, par circonscription et parti qualifié (voir
    `scripts/analyses/win_probability_calibration.py`)."""
    path = SENSITIVITY_DIR / f"win-probability-calibration-{model}.csv"
    data = pd.read_csv(path)
    accent = "#3987e5" if dark else "#2a78d6"
    muted = "#aeb4c0" if dark else "#5a616e"

    axis_pct = alt.Axis(format=".0%", values=[0, 0.25, 0.5, 0.75, 1])
    # Graduations tous les 10 % en x : les points sont trop resserrés vers les
    # extrêmes pour se situer précisément avec seulement les repères de 25 %.
    # Un label sur deux (multiples de 20 %) pour ne pas surcharger l'axe ; les
    # graduations intermédiaires (10 %, 30 %...) restent visibles sans texte.
    axis_pct_x = alt.Axis(
        format=".0%",
        values=[i / 20 for i in range(21)],
        labelExpr="datum.value % 0.2 < 0.001 ? format(datum.value, '.0%') : ''",
    )
    x_title = "Probabilité de victoire prédite"
    y_title = "Fréquence réalisée"
    x_scale = alt.Scale(domain=[0, 1])
    y_scale = alt.Scale(domain=[0, 1])
    # Chaque couche superposée déclare le MÊME titre/axe/échelle, même quand
    # son champ diffère (`x`/`y` pour la diagonale, `ic95_bas`/`ic95_haut`
    # pour la bande) : Vega-Lite fusionne les axes d'un layered chart, et deux
    # couches en désaccord sur le titre le concatènent (« x, predit_moyen »)
    # plutôt que d'en choisir un — au lieu de « axis=None » sur les couches en
    # trop, qui supprime l'axe fusionné en entier pour toutes les couches.
    diagonal = (
        alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]}))
        .mark_line(strokeDash=[3, 3], color=muted, strokeWidth=1.3)
        .encode(
            x=alt.X("x:Q", title=x_title, axis=axis_pct_x, scale=x_scale),
            y=alt.Y("y:Q", title=y_title, axis=axis_pct, scale=y_scale),
        )
    )
    base = alt.Chart(data).encode(
        x=alt.X("predit_moyen:Q", title=x_title, axis=axis_pct_x, scale=x_scale),
        y=alt.Y("realise:Q", title=y_title, axis=axis_pct, scale=y_scale),
    )
    tooltip = [
        alt.Tooltip("predit_min:Q", title="Prédit, borne basse", format=".0%"),
        alt.Tooltip("predit_max:Q", title="Prédit, borne haute", format=".0%"),
        alt.Tooltip("realise:Q", title="Réalisé", format=".1%"),
        alt.Tooltip("ic95_bas:Q", title="IC 95 %, bas", format=".1%"),
        alt.Tooltip("ic95_haut:Q", title="IC 95 %, haut", format=".1%"),
        alt.Tooltip("n:Q", title="Cellules dans la tranche"),
    ]
    # Pas de canal `order` ici : sur un mark_area/mark_line, une valeur
    # quantitative posée sur `order` fait éclater la bande en un segment
    # disjoint par point plutôt que de la trier — `predit_moyen` est déjà
    # croissant dans le CSV (tranches construites dans cet ordre), ce qui
    # suffit à connecter les points correctement.
    band = base.mark_area(color=accent, opacity=0.22, interpolate="monotone").encode(
        y=alt.Y("ic95_bas:Q", title=y_title, axis=axis_pct, scale=y_scale),
        y2="ic95_haut:Q",
        tooltip=tooltip,
    )
    lower = base.mark_line(
        color=accent, strokeWidth=1.6, opacity=0.85, interpolate="monotone"
    ).encode(
        y=alt.Y("ic95_bas:Q", title=y_title, axis=axis_pct, scale=y_scale),
        tooltip=tooltip,
    )
    upper = base.mark_line(
        color=accent, strokeWidth=1.6, opacity=0.85, interpolate="monotone"
    ).encode(
        y=alt.Y("ic95_haut:Q", title=y_title, axis=axis_pct, scale=y_scale),
        tooltip=tooltip,
    )
    # Repères ponctuels à chaque tranche, par-dessus la bande interpolée : elle
    # lisse entre les tranches, ces traits rappellent où sont les vraies
    # observations.
    error_bars = base.mark_rule(color=accent, strokeWidth=1.4, opacity=0.55).encode(
        y=alt.Y("ic95_bas:Q", title=y_title, axis=axis_pct, scale=y_scale),
        y2="ic95_haut:Q",
        tooltip=tooltip,
    )
    chart = (diagonal + band + lower + upper + error_bars).properties(
        width=420,
        height=420,
        title={
            "text": "Calibration des probabilités de victoire locales",
            "subtitle": [
                f"Modèle {model} · circonscriptions et partis qualifiés,",
                "déciles à effectif égal, IC 95 % de Wilson par tranche",
            ],
        },
    )
    return _style(chart, dark=dark)


def simulation_parameter_draws_chart(*, dark: bool = False) -> alt.Chart:
    """Four priors and the illustrative draw used in the 0101 walkthrough."""
    panels = [
        (
            "Concentration α",
            "Flux 1",
            np.linspace(*DEFAULT_DIRICHLET_ALPHA_BOUNDS, 160),
            lambda x: 1
            / (
                x
                * np.log(
                    DEFAULT_DIRICHLET_ALPHA_BOUNDS[1]
                    / DEFAULT_DIRICHLET_ALPHA_BOUNDS[0]
                )
            ),
            ".2f",
        ),
        (
            "Démobilisation d",
            "Flux 2",
            np.linspace(0.0001, 0.25, 160),
            lambda x: beta.pdf(x, *DEFAULT_QUALIFIED_DEMOBILISATION_PRIOR),
            ".0%",
        ),
        (
            "Rétention des non-exprimés",
            "Flux 3",
            np.linspace(0.45, 0.9999, 160),
            lambda x: beta.pdf(x, *DEFAULT_NON_EXPRESSED_RETENTION_PRIOR),
            ".0%",
        ),
        (
            "Tilt τ",
            "Flux 3",
            np.linspace(*DEFAULT_NON_EXPRESSED_TILT_BOUNDS, 160),
            lambda x: np.full_like(x, 0.5),
            ".1f",
        ),
    ]
    rows: list[dict[str, object]] = []
    # Le repère orange vaut UNE ligne par panneau : le brancher sur la grille de
    # densité en dessinait 160 copies exactement superposées (voir
    # `anchored_parameter_draws_chart`).
    markers: list[dict] = []
    for order, (parameter, flux, values, density, value_format) in enumerate(panels):
        selected = SIMULATION_EXAMPLE_DRAWS[parameter]
        selected_density = float(density(np.array([selected]))[0])
        rows.extend(
            {
                "parameter": parameter,
                "flux": flux,
                "order": order,
                "x": float(x),
                "density": float(y),
            }
            for x, y in zip(values, density(values))
        )
        markers.append(
            {
                "parameter": parameter,
                "selected": selected,
                "selected_density": selected_density,
                "selected_label": format(selected, value_format),
            }
        )

    data = pl.DataFrame(rows)
    marker_data = pl.DataFrame(markers)
    accent = "#e49a55" if dark else "#b56824"
    muted = "#aeb4c0" if dark else "#7b818c"
    panel_charts = []
    for parameter, flux, *_ in panels:
        panel_data = data.filter(pl.col("parameter") == parameter)
        panel_marker = marker_data.filter(pl.col("parameter") == parameter)
        base = alt.Chart(panel_data).encode(
            x=alt.X(
                "x:Q",
                title=flux,
                axis=alt.Axis(tickCount=3, grid=False, titlePadding=8),
            ),
            y=alt.Y("density:Q", title=None, axis=None),
        )
        panel_charts.append(
            alt.layer(
                base.mark_area(color=muted, opacity=0.16),
                base.mark_line(color=muted, strokeWidth=1.5),
                alt.Chart(panel_marker)
                .mark_rule(color=accent, strokeWidth=2)
                .encode(x="selected:Q"),
                alt.Chart(panel_marker)
                .mark_point(
                    color=accent,
                    filled=True,
                    size=55,
                    stroke="white",
                    strokeWidth=1,
                )
                .encode(x="selected:Q", y="selected_density:Q"),
                alt.Chart(panel_marker)
                .mark_text(
                    color=accent,
                    align="center",
                    baseline="bottom",
                    dy=-4,
                    fontWeight=500,
                )
                .encode(
                    x="selected:Q",
                    y="selected_density:Q",
                    text="selected_label:N",
                ),
            ).properties(
                width=128,
                height=72,
                title=alt.TitleParams(
                    parameter, anchor="middle", fontSize=11, fontWeight=400
                ),
            )
        )

    chart = (
        alt.hconcat(*panel_charts, spacing=14)
        .properties(
            title=alt.TitleParams(
                "Un tirage parmi les valeurs possibles",
                subtitle="La courbe représente le prior ; le repère orange, la valeur retenue dans l’exemple.",
                fontWeight=500,
            )
        )
        .resolve_scale(x="independent", y="independent")
    )
    return _style(chart, dark=dark)


def _anchored_prior_panel_groups():
    """Panel specifications shared by the two prior-summary figures."""
    districts = load_full_results().districts
    shares_and_weights = []
    for district in districts:
        expressed = sum(district.competing_parties_results.values()) + sum(
            district.eliminated_parties_results.values()
        )
        registered = expressed + district.non_expressed
        shares_and_weights.append((expressed / registered, registered))
    shares = np.array([share for share, _ in shares_and_weights])
    weights = np.array([weight for _, weight in shares_and_weights])
    national_share = float(weights @ shares / weights.sum())
    centre = national_share + DEFAULT_EXPECTED_EXPRESSED_CHANGE_PTS / 100

    def logit_sigma(band_points: float) -> float:
        anchor = logit(centre)
        band = band_points / 100
        distance = min(
            abs(logit(centre - band) - anchor),
            abs(logit(centre + band) - anchor),
        )
        return float(distance / norm.ppf(0.95))

    national_sigma = logit_sigma(DEFAULT_NATIONAL_EXPRESSED_BAND_PTS)
    district_sigma = logit_sigma(DEFAULT_DISTRICT_EXPRESSED_BAND_PTS)
    shared_panels = [
        (
            "Concentration α",
            np.linspace(*DEFAULT_DIRICHLET_ALPHA_BOUNDS, 160),
            lambda x: 1
            / (
                x
                * np.log(
                    DEFAULT_DIRICHLET_ALPHA_BOUNDS[1]
                    / DEFAULT_DIRICHLET_ALPHA_BOUNDS[0]
                )
            ),
            ".2f",
        ),
        (
            "Démobilisation d",
            np.linspace(0.0001, 0.25, 160),
            lambda x: beta.pdf(x, *DEFAULT_QUALIFIED_DEMOBILISATION_PRIOR),
            ".0%",
        ),
        (
            "Rétention des non-exprimés",
            np.linspace(0.5, 0.9999, 160),
            lambda x: beta.pdf(x, *DEFAULT_NON_EXPRESSED_RETENTION_PRIOR),
            ".0%",
        ),
        (
            "Tilt τ",
            np.linspace(*DEFAULT_NON_EXPRESSED_TILT_BOUNDS, 160),
            lambda x: np.full_like(x, 0.5),
            ".1f",
        ),
    ]
    anchoring_panels = [
        (
            "Dérive nationale δnat",
            np.linspace(-3 * national_sigma, 3 * national_sigma, 160),
            lambda x: norm.pdf(x, 0, national_sigma),
            ".2f",
        ),
        (
            "Écart local δ0101",
            np.linspace(-3 * district_sigma, 3 * district_sigma, 160),
            lambda x: norm.pdf(x, 0, district_sigma),
            ".2f",
        ),
    ]
    local_panels = [
        (
            "Mélange national λ",
            np.linspace(0.0001, 0.9999, 160),
            lambda x: beta.pdf(x, *DEFAULT_MIXING_PRIOR),
            ".2f",
        ),
        (
            "Corrélation département ρd",
            np.linspace(0.0001, 0.9999, 160),
            lambda x: beta.pdf(x, *DEFAULT_DEPARTMENT_CORRELATION_PRIOR),
            ".2f",
        ),
        (
            "Corrélation région ρr",
            np.linspace(0.0001, 0.9999, 160),
            lambda x: beta.pdf(x, *DEFAULT_REGION_CORRELATION_PRIOR),
            ".2f",
        ),
    ]
    return shared_panels, anchoring_panels, local_panels


def anchored_parameter_draws_chart(*, dark: bool = False) -> alt.Chart:
    """Priors and illustrative values for the locally anchored model."""
    shared_panels, anchoring_panels, local_panels = _anchored_prior_panel_groups()

    accent = "#e49a55" if dark else "#b56824"
    muted = "#aeb4c0" if dark else "#7b818c"

    def panel_chart(panel):
        parameter, values, density, value_format = panel
        selected = ANCHORED_EXAMPLE_DRAWS[parameter]
        selected_density = float(density(np.array([selected]))[0])
        data = pl.DataFrame({"x": values, "density": density(values)})
        # UNE ligne, pas une par point de la grille : le repère est un seul
        # marqueur. Le lier à `data` en dessinait 160 exemplaires superposés —
        # invisible à l'écran, mais l'export SVG les écrivait tous (922 Ko).
        marker = pl.DataFrame(
            {
                "selected": [selected],
                "selected_density": [selected_density],
                "selected_label": [format(selected, value_format)],
            }
        )
        base = alt.Chart(data).encode(
            x=alt.X("x:Q", title=None, axis=alt.Axis(tickCount=3, grid=False)),
            y=alt.Y("density:Q", title=None, axis=None),
        )
        return alt.layer(
            base.mark_area(color=muted, opacity=0.16),
            base.mark_line(color=muted, strokeWidth=1.5),
            alt.Chart(marker)
            .mark_rule(color=accent, strokeWidth=2)
            .encode(x="selected:Q"),
            alt.Chart(marker)
            .mark_point(
                color=accent, filled=True, size=55, stroke="white", strokeWidth=1
            )
            .encode(x="selected:Q", y="selected_density:Q"),
            alt.Chart(marker)
            .mark_text(
                color=accent,
                align="center",
                baseline="bottom",
                dy=-4,
                fontWeight=500,
            )
            .encode(
                x="selected:Q",
                y="selected_density:Q",
                text="selected_label:N",
            ),
        ).properties(
            width=128,
            height=72,
            title=alt.TitleParams(
                parameter, anchor="middle", fontSize=11, fontWeight=400
            ),
        )

    shared = alt.hconcat(
        *(panel_chart(panel) for panel in shared_panels), spacing=14
    ).properties(
        title=alt.TitleParams(
            "Paramètres partagés avec le modèle national",
            fontSize=11,
            fontWeight=500,
        )
    )
    anchoring = alt.hconcat(
        *(panel_chart(panel) for panel in anchoring_panels), spacing=14
    ).properties(
        title=alt.TitleParams(
            "Paramètres d’ancrage de l’abstention", fontSize=11, fontWeight=500
        )
    )
    local = alt.hconcat(
        *(panel_chart(panel) for panel in local_panels), spacing=14
    ).properties(
        title=alt.TitleParams("Paramètres locaux", fontSize=11, fontWeight=500)
    )
    chart = alt.vconcat(shared, anchoring, local, spacing=20).properties(
        title=alt.TitleParams(
            "Un tirage du modèle local ancré",
            subtitle="Les courbes représentent les priors ; les repères orange, les valeurs de l’exemple.",
            fontWeight=500,
        )
    )
    return _style(chart, dark=dark)


def _prior_uniform_comparison(panel) -> pl.DataFrame:
    """Un prior et sa référence uniforme, sur une grille commune."""
    parameter, original_values, density, _ = panel
    if parameter == "Démobilisation d":
        # Bornes NATURELLES d'une proportion — pas la fenêtre [0, 0.25]
        # utilisée ailleurs pour zoomer sur la masse du prior. Comparer à
        # l'uniforme sur cette fenêtre étroite aurait été arbitraire ; [0, 1]
        # est le seul support qui ne dépend d'aucun choix de cadrage.
        values = np.linspace(0.0001, 0.9999, 241)
    else:
        # Tilt τ compris : ses bornes déclarées (`non_expressed_tilt_uniform`,
        # ±1) SONT son support réel, pas une fenêtre de confort — les élargir
        # artificiellement ferait apparaître un écart à l'uniforme qui
        # n'existe pas (le prior choisi EST l'uniforme sur ce support).
        values = np.linspace(original_values[0], original_values[-1], 241)
    prior = density(values)
    reference = np.full_like(values, 1 / (values[-1] - values[0]))
    return pl.DataFrame(
        {
            "x": values,
            "prior": prior,
            "reference": reference,
            "lower": np.minimum(prior, reference),
            "upper": np.maximum(prior, reference),
            "hatch": np.arange(len(values)) % 6 == 0,
        }
    )


def _prior_divergence_bits() -> dict[str, float]:
    """Divergence de Kullback-Leibler de chaque prior à sa référence uniforme.

    En bits, sur la grille des panneaux. Partagée par les deux figures de
    priors, pour qu'elles ne puissent pas diverger sur la même quantité.
    """
    groups = _anchored_prior_panel_groups()
    bits = {}
    for panel in (panel for group in groups for panel in group):
        data = _prior_uniform_comparison(panel)
        prior = data["prior"].to_numpy()
        reference = data["reference"].to_numpy()
        kl = np.trapezoid(prior * np.log(prior / reference), data["x"].to_numpy())
        bits[panel[0]] = float(kl) / np.log(2)
    return bits


def prior_information_chart(*, dark: bool = False) -> alt.Chart:
    """Chosen priors compared with explicit uniform reference distributions."""
    shared_panels, anchoring_panels, local_panels = _anchored_prior_panel_groups()
    accent = "#e49a55" if dark else "#b56824"
    muted = "#aeb4c0" if dark else "#6d7480"
    comparison_data = _prior_uniform_comparison

    def panel_chart(panel):
        parameter = panel[0]
        data = comparison_data(panel)
        # Domaine cadré exactement sur le support tracé : sans `scale` explicite,
        # Vega-Lite arrondit à un domaine « joli » (p. ex. Concentration α,
        # support [0.5, 1.0], se voyait étendu à 0 — 40 % du panneau en blanc,
        # avant la première valeur réellement définie). Le même objet `x_scale`
        # sur les trois couches évite aussi que leurs domaines divergent et se
        # concatènent dans le titre d'axe (cf. le graphique de calibration).
        x_scale = alt.Scale(
            domain=[float(data["x"].min()), float(data["x"].max())], nice=True
        )
        x_axis = alt.Axis(tickCount=3, grid=False)
        axes = dict(
            x=alt.X("x:Q", title=None, axis=x_axis, scale=x_scale),
            y=alt.Y("prior:Q", title=None, axis=None),
        )
        hatch = (
            alt.Chart(data.filter("hatch"))
            .mark_rule(color=muted, opacity=0.38, strokeWidth=0.7)
            .encode(
                x=alt.X("x:Q", title=None, axis=x_axis, scale=x_scale),
                y=alt.Y("lower:Q", title=None, axis=None),
                y2="upper:Q",
            )
        )
        reference = (
            alt.Chart(data)
            .mark_line(color=muted, strokeDash=[4, 3], strokeWidth=1.4)
            .encode(
                x=alt.X("x:Q", title=None, axis=x_axis, scale=x_scale),
                y=alt.Y("reference:Q", title=None, axis=None),
            )
        )
        prior = alt.Chart(data).mark_line(color=accent, strokeWidth=2).encode(**axes)
        layers = [hatch, reference, prior]
        if np.allclose(data["prior"].to_numpy(), data["reference"].to_numpy()):
            # Tilt τ : le prior retenu EST l'uniforme sur son support, donc rien
            # à hachurer — sans ce mot, un panneau presque vide à côté de sept
            # autres bien remplis se lirait comme un graphique cassé plutôt que
            # comme le seul cas où le modèle n'ajoute aucune information.
            layers.append(
                alt.Chart(pl.DataFrame({"label": ["prior = référence uniforme"]}))
                .mark_text(color=muted, fontSize=9, fontStyle="italic", opacity=0.85)
                .encode(x=alt.value(64), y=alt.value(48), text=alt.Text("label:N"))
            )
        return alt.layer(*layers).properties(
            width=128,
            height=72,
            title=alt.TitleParams(
                parameter, anchor="middle", fontSize=11, fontWeight=400
            ),
        )

    def group_chart(panels, title):
        return alt.hconcat(
            *(panel_chart(panel) for panel in panels), spacing=14
        ).properties(title=alt.TitleParams(title, fontSize=11, fontWeight=500))

    chart = alt.vconcat(
        group_chart(shared_panels, "Paramètres partagés avec le modèle national"),
        group_chart(anchoring_panels, "Paramètres d’ancrage de l’abstention"),
        group_chart(local_panels, "Paramètres locaux"),
        spacing=20,
    ).properties(
        title=alt.TitleParams(
            "Où le modèle s’écarte d’une référence uniforme",
            subtitle="Orange : prior retenu · pointillé : référence uniforme · hachures : écart entre les deux.",
            fontWeight=500,
        )
    )
    return _style(chart, dark=dark)


def parameter_influence_chart(
    *,
    model: str = "kernel_anchored",
    parties: tuple[str, ...] = ("RN+",),
    dark: bool = False,
) -> alt.Chart:
    """Effect of each parameter on the median and predictive interval width."""
    path = SENSITIVITY_DIR / f"parameter-influence-{model}.csv"
    data = pl.read_csv(path)
    bits = _prior_divergence_bits()
    groups = {
        "Concentration α": "Paramètres nationaux",
        "Démobilisation d": "Paramètres nationaux",
        "Rétention des non-exprimés": "Paramètres nationaux",
        "Tilt τ": "Paramètres nationaux",
        "Dérive nationale δnat": "Ancrage de l’abstention",
        "Écart local δ0101": "Ancrage de l’abstention",
        "Mélange national λ": "Variations locales",
        "Corrélation département ρd": "Variations locales",
        "Corrélation région ρr": "Variations locales",
    }
    short_labels = {
        "Concentration α": "α",
        "Démobilisation d": "d",
        "Rétention des non-exprimés": "rNE",
        "Tilt τ": "τ",
        "Dérive nationale δnat": "δnat",
        "Écart local δ0101": "δ0101",
        "Mélange national λ": "λ",
        "Corrélation département ρd": "ρd",
        "Corrélation région ρr": "ρr",
    }
    data = (
        data.filter(pl.col("parti").is_in(parties))
        .with_columns(
            pl.col("parametre").replace_strict(bits, default=None).alias("bits"),
            pl.col("parametre").replace_strict(groups).alias("groupe"),
            pl.col("parametre").replace_strict(short_labels).alias("etiquette"),
        )
        .drop_nulls("bits")
        .sort("amplitude_p50")
    )

    muted = "#aeb4c0" if dark else "#6d7480"
    group_domain = [
        "Paramètres nationaux",
        "Ancrage de l’abstention",
        "Variations locales",
    ]
    group_range = (
        ["#e49a55", "#62b6b2", "#a7a9dc"] if dark else ["#b56824", "#287271", "#5b5f97"]
    )
    colour = alt.Color(
        "groupe:N",
        scale=alt.Scale(domain=group_domain, range=group_range),
        legend=alt.Legend(title=None, orient="top"),
    )

    x_limit = (
        max(float(data["amplitude_p50"].max()), float(data["plancher_p50"].max()))
        * 1.18
    )
    y_limit = (
        max(
            float(data["amplitude_largeur"].max()),
            float(data["plancher_largeur"].max()),
        )
        * 1.18
    )
    x_scale = alt.Scale(domain=[0, x_limit])
    y_scale = alt.Scale(domain=[0, y_limit])
    x_title = "Amplitude du déplacement de la médiane (sièges)"
    y_title = "Amplitude de la largeur de l’intervalle à 90 % (sièges)"
    x_enc = alt.X(
        "amplitude_p50:Q",
        title=x_title,
        scale=x_scale,
        axis=alt.Axis(tickCount=7),
    )
    y_enc = alt.Y(
        "amplitude_largeur:Q",
        title=y_title,
        scale=y_scale,
        axis=alt.Axis(tickCount=7),
    )

    noise = data.group_by("parti").agg(
        pl.lit(0.0).alias("x_min"),
        pl.col("plancher_p50").max().alias("x_max"),
        pl.lit(0.0).alias("y_min"),
        pl.col("plancher_largeur").max().alias("y_max"),
    )
    noise_zone = (
        alt.Chart(noise)
        .mark_rect(color=muted, opacity=0.11)
        .encode(
            x=alt.X("x_min:Q", scale=x_scale, title=x_title),
            x2="x_max:Q",
            y=alt.Y("y_min:Q", scale=y_scale, title=y_title),
            y2="y_max:Q",
        )
    )
    zero_lines = pl.DataFrame({"parti": list(parties), "zero": [0.0] * len(parties)})
    zero_vertical = (
        alt.Chart(zero_lines)
        .mark_rule(color=muted, strokeWidth=1)
        .encode(x=alt.X("zero:Q", scale=x_scale, title=x_title))
    )
    zero_horizontal = (
        alt.Chart(zero_lines)
        .mark_rule(color=muted, strokeWidth=1)
        .encode(y=alt.Y("zero:Q", scale=y_scale, title=y_title))
    )

    tooltip = [
        alt.Tooltip("parametre:N", title="Paramètre"),
        alt.Tooltip("amplitude_p50:Q", title="Amplitude de médiane", format=".1f"),
        alt.Tooltip("amplitude_largeur:Q", title="Amplitude de largeur", format=".1f"),
        alt.Tooltip("plancher_p50:Q", title="Seuil médiane", format=".1f"),
        alt.Tooltip("plancher_largeur:Q", title="Seuil largeur", format=".1f"),
        alt.Tooltip("bits:Q", title="Information du prior (bits)", format=".2f"),
    ]
    zero_information = (
        alt.Chart(data.filter(pl.col("bits") == 0))
        .mark_circle(filled=False, size=48, strokeWidth=1.4)
        .encode(x=x_enc, y=y_enc, color=colour, tooltip=tooltip)
    )
    bubbles = (
        alt.Chart(data.filter(pl.col("bits") > 0))
        .mark_circle(filled=True, opacity=0.72)
        .encode(
            x=x_enc,
            y=y_enc,
            color=colour,
            size=alt.Size(
                "bits:Q",
                title="Quantité d'information ajoutée",
                scale=alt.Scale(domain=[0, float(data["bits"].max())], range=[0, 900]),
                legend=alt.Legend(
                    orient="right",
                    tickCount=3,
                    symbolFillColor=muted,
                    labelColor=muted,
                    titleColor=muted,
                ),
            ),
            tooltip=tooltip,
        )
    )

    label_positions = {
        "Concentration α": ("left", 7, -9),
        "Démobilisation d": ("left", 18, 11),
        "Tilt τ": ("right", -7, -13),
        "Dérive nationale δnat": ("left", 7, -8),
        "Écart local δ0101": ("left", 7, 11),
        "Mélange national λ": ("left", 7, -5),
        "Corrélation département ρd": ("right", -7, 12),
        "Corrélation région ρr": ("right", -7, -2),
    }
    influential = data.filter(pl.col("decale_vraiment") | pl.col("elargit_vraiment"))
    labels = [
        alt.Chart(influential.filter(pl.col("parametre") == parameter))
        .mark_text(
            color=muted,
            fontSize=9,
            fontWeight=500,
            align=align,
            dx=dx,
            dy=dy,
        )
        .encode(
            x=x_enc,
            y=y_enc,
            text=alt.Text("parametre:N" if len(parties) == 1 else "etiquette:N"),
        )
        for parameter, (align, dx, dy) in label_positions.items()
    ]

    quiet_parameters = {
        row["parti"]: ", ".join(row["etiquette"])
        for row in (
            data.filter(~(pl.col("decale_vraiment") | pl.col("elargit_vraiment")))
            .sort("parametre")
            .group_by("parti", maintain_order=True)
            .agg("etiquette")
            .iter_rows(named=True)
        )
    }
    quadrant_rows = []
    for party in parties:
        quadrant_rows.extend(
            [
                {
                    "parti": party,
                    "x": 0.03 * x_limit,
                    "y": 0.94 * y_limit,
                    "label": "Surtout\nincertitude",
                    "position": "top_left",
                },
                {
                    "parti": party,
                    "x": 0.96 * x_limit,
                    "y": 0.94 * y_limit,
                    "label": "Médiane et\nincertitude",
                    "position": "top_right",
                },
                {
                    "parti": party,
                    "x": 0.03 * x_limit,
                    "y": 0.03 * y_limit,
                    "label": "Effet faible",
                    "position": "noise",
                },
                {
                    "parti": party,
                    "x": 0.96 * x_limit,
                    "y": 0.04 * y_limit,
                    "label": "Surtout\nmédiane",
                    "position": "bottom_right",
                },
            ]
        )
    quadrant_data = pl.DataFrame(quadrant_rows)

    def quadrant_labels(position, *, align, baseline):
        return (
            alt.Chart(quadrant_data.filter(pl.col("position") == position))
            .mark_text(
                align=align,
                baseline=baseline,
                color=muted,
                fontSize=8,
                fontStyle="italic",
                lineBreak="\n",
                lineHeight=11,
                opacity=0.82,
            )
            .encode(
                x=alt.X("x:Q", scale=x_scale, title=x_title),
                y=alt.Y("y:Q", scale=y_scale, title=y_title),
                text="label:N",
            )
        )

    panel_layers = [
        noise_zone,
        zero_vertical,
        zero_horizontal,
        zero_information,
        bubbles,
        *labels,
        quadrant_labels("top_left", align="left", baseline="top"),
        quadrant_labels("top_right", align="right", baseline="top"),
        quadrant_labels("noise", align="left", baseline="bottom"),
        quadrant_labels("bottom_right", align="right", baseline="bottom"),
    ]
    panels = [
        alt.layer(
            *(
                layer.transform_filter(alt.datum.parti == party)
                for layer in panel_layers
            )
        ).properties(
            width=500 if len(parties) == 1 else 225,
            height=340 if len(parties) == 1 else 280,
            title=alt.TitleParams(
                party,
                subtitle=f"Sous le bruit : {quiet_parameters.get(party, '—')}",
                anchor="middle",
                fontSize=12,
                fontWeight=600,
                subtitleColor=muted,
                subtitleFontSize=8,
                subtitleFontStyle="italic",
            ),
        )
        for party in parties
    ]
    scope_subtitle = (
        f"Sièges {parties[0]} · modèle {model} · rectangle gris : deux effets indiscernables du bruit."
        if len(parties) == 1
        else f"Modèle {model} · rectangle gris propre à chaque parti : deux effets indiscernables du bruit."
    )
    chart = (
        alt.hconcat(*panels, spacing=14)
        .properties(
            title={
                "text": "Quels paramètres déplacent ou élargissent la prévision ?",
                "subtitle": [
                    "Position : amplitude observée entre les dix déciles. Taille : information injectée par le prior.",
                    scope_subtitle,
                ],
            },
        )
        .resolve_scale(x="shared", y="shared", color="shared", size="shared")
    )
    return _style(chart, dark=dark)


def parameter_interval_chart(
    *, model: str = "kernel_anchored", party: str = "RN+", dark: bool = False
) -> alt.Chart:
    """Ce que chaque paramètre déplace de l'INTERVALLE, pas de la moyenne.

    Un indice de sensibilité classique ne suit que la moyenne conditionnelle et
    rate donc les paramètres de pure dispersion. Ici chaque ligne compare
    l'intervalle à 90 % obtenu quand le paramètre est dans son décile le plus
    bas à celui obtenu dans son décile le plus haut : un déplacement horizontal
    se lit comme un décalage, un changement de longueur comme un
    resserrement ou un élargissement.
    """
    profile = pl.read_csv(
        SENSITIVITY_DIR / f"parameter-interval-profile-{model}.csv"
    ).filter(pl.col("parti") == party)
    swings = pl.read_csv(
        SENSITIVITY_DIR / f"parameter-interval-swing-{model}.csv"
    ).filter(pl.col("parti") == party)

    reference = profile.filter(pl.col("decile") == -1)
    ref_p05 = float(reference["p05"][0])
    ref_p50 = float(reference["p50"][0])
    ref_p95 = float(reference["p95"][0])

    conditioned = profile.filter(pl.col("decile") >= 0)
    bottom = conditioned.filter(pl.col("decile") == conditioned["decile"].min())
    top = conditioned.filter(pl.col("decile") == conditioned["decile"].max())

    bits = _prior_divergence_bits()
    order = swings.sort("amplitude_max", descending=True)["parametre"].to_list()
    data = pl.concat(
        [
            bottom.with_columns(pl.lit("décile le plus bas").alias("condition")),
            top.with_columns(pl.lit("décile le plus haut").alias("condition")),
        ]
    ).with_columns(
        pl.col("parametre").replace_strict(bits, default=None).alias("bits"),
        (pl.col("p95") - pl.col("p05")).alias("largeur"),
    )

    accent = "#e49a55" if dark else "#b56824"
    muted = "#aeb4c0" if dark else "#6d7480"

    span = max(ref_p95 - ref_p05, 1.0)
    x_scale = alt.Scale(
        domain=[
            min(float(data["p05"].min()), ref_p05) - span * 0.12,
            max(float(data["p95"].max()), ref_p95) + span * 0.12,
        ]
    )
    x_enc = alt.X(
        "p05:Q", title=f"Sièges {party}", scale=x_scale, axis=alt.Axis(format="d")
    )
    y_enc = alt.Y(
        "parametre:N",
        title=None,
        sort=order,
        axis=alt.Axis(labelFontSize=10.5, domain=False, ticks=False, labelLimit=200),
    )
    colour = alt.Color(
        "condition:N",
        scale=alt.Scale(
            domain=["décile le plus bas", "décile le plus haut"],
            range=[muted, accent],
        ),
        legend=alt.Legend(title=None, orient="top", offset=2, labelFontSize=10.5),
    )
    offset = alt.YOffset(
        "condition:N",
        scale=alt.Scale(domain=["décile le plus bas", "décile le plus haut"]),
    )

    # Intervalle non conditionné, en fond : la référence que publie le billet.
    band = (
        alt.Chart(pd.DataFrame({"x": [ref_p05], "x2": [ref_p95]}))
        .mark_rect(color=muted, opacity=0.13)
        .encode(x=alt.X("x:Q", scale=x_scale, title=None), x2="x2:Q")
    )
    median_rule = (
        alt.Chart(pd.DataFrame({"x": [ref_p50]}))
        .mark_rule(color=muted, strokeDash=[4, 3], strokeWidth=1)
        .encode(x=alt.X("x:Q", scale=x_scale, title=None))
    )

    tooltip = [
        alt.Tooltip("parametre:N", title="Paramètre"),
        alt.Tooltip("condition:N", title="Condition"),
        alt.Tooltip("p05:Q", title="p05", format=".0f"),
        alt.Tooltip("p50:Q", title="Médiane", format=".0f"),
        alt.Tooltip("p95:Q", title="p95", format=".0f"),
        alt.Tooltip("largeur:Q", title="Largeur", format=".0f"),
        alt.Tooltip("bits:Q", title="Croyance (bits)", format=".2f"),
    ]
    base = alt.Chart(data)
    bars = base.mark_rule(strokeWidth=3.4, opacity=0.92).encode(
        x=x_enc, x2="p95:Q", y=y_enc, yOffset=offset, color=colour, tooltip=tooltip
    )
    medians = base.mark_point(
        shape="diamond", filled=True, size=42, stroke="white", strokeWidth=0.8
    ).encode(
        x=alt.X("p50:Q", scale=x_scale, title=None),
        y=y_enc,
        yOffset=offset,
        color=colour,
        tooltip=tooltip,
    )

    # Verdict par paramètre, à droite : « décale » quand l'amplitude de la
    # médiane dépasse son plancher de bruit, « élargit » quand celle de la
    # largeur dépasse le sien. Un `max - min` sur dix déciles est un maximum de
    # quantités bruitées, donc jamais nul : sans ces planchers, les huit
    # paramètres sembleraient tous faire quelque chose.
    # La croyance injectée est rappelée à côté du verdict : sans elle il
    # faudrait lire deux figures pour rapprocher les deux questions — ce que le
    # prior suppose, et ce que cela déplace.
    def _verdict(row) -> str:
        if row["decale_vraiment"] and row["elargit_vraiment"]:
            effect = "décale et élargit"
        elif row["decale_vraiment"]:
            effect = "décale"
        elif row["elargit_vraiment"]:
            effect = "élargit"
        else:
            effect = "sans effet net"
        value = f"{bits[row['parametre']]:.2f}".replace(".", ",")
        return f"{effect}  ·  {value} bit"

    verdicts = pl.DataFrame(
        [
            {"parametre": row["parametre"], "verdict": _verdict(row)}
            for row in swings.iter_rows(named=True)
        ]
    )
    verdict_labels = (
        alt.Chart(verdicts)
        .mark_text(color=muted, fontSize=9.5, align="left", fontStyle="italic")
        .encode(
            # `y_enc`, et surtout pas `axis=None` : sur un graphique superposé,
            # une seule couche qui annule l'axe le supprime pour TOUTES (les
            # noms de paramètres avaient disparu du cadre).
            x=alt.value(437),
            y=y_enc,
            text="verdict:N",
        )
    )

    chart = alt.layer(band, median_rule, bars, medians, verdict_labels).properties(
        width=430,
        height=alt.Step(30),
        title={
            "text": "Décaler l’intervalle et l’élargir sont deux choses distinctes",
            "subtitle": [
                "Intervalle à 90 % des sièges quand le paramètre est dans son"
                " décile le plus bas, puis le plus haut.",
                f"Losange : médiane. Bande grise et pointillé : l’intervalle"
                f" complet, [{ref_p05:.0f} — {ref_p95:.0f}], médiane"
                f" {ref_p50:.0f}. Mention à droite : ce qui dépasse le"
                " plancher de bruit.",
            ],
        },
    )
    return _style(chart, dark=dark)


def write_classic_charts(output_dir: Path = OUTPUT_DIR) -> None:
    """Export every conventional chart through Altair's official SVG backend."""
    output_dir.mkdir(parents=True, exist_ok=True)
    charts = {
        "pollster-intervals": pollster_intervals_chart,
        "pollster-vs-model": pollster_vs_model_chart,
        "withdrawals": withdrawals_chart,
        "kernel-sensitivity": kernel_sensitivity_chart,
        "seats-by-non-expressed": seats_non_expressed_chart,
        "alpha-sensitivity": alpha_sensitivity_chart,
        "demobilisation-sensitivity": demobilisation_sensitivity_chart,
        "seat-results": seat_results_chart,
        "conditioned-seat-results": conditioned_seat_results_chart,
        "joint-predictive-region": joint_region_chart,
        "dominant-party": dominant_party_chart,
        "joint-seats": joint_seats_chart,
        "expressed-share": expressed_share_chart,
        "district-0101-national-delta": district_0101_national_delta_chart,
        "district-expressed-error": district_expressed_error_chart,
        "dirichlet-simplex": simplex_chart,
        "tilt-effect": tilt_effect_chart,
        "simulation-parameter-draws": simulation_parameter_draws_chart,
        "anchored-parameter-draws": anchored_parameter_draws_chart,
        "prior-information": prior_information_chart,
        "parameter-influence": parameter_influence_chart,
        "parameter-interval": parameter_interval_chart,
        "win-probability-calibration": win_probability_calibration_chart,
    }
    for name, build_chart in charts.items():
        for suffix, dark in [("", False), ("-dark", True)]:
            path = output_dir / f"{name}{suffix}.svg"
            build_chart(dark=dark).save(path)
            print(f"wrote {path.relative_to(PROJECT_ROOT)} (Altair)")


if __name__ == "__main__":
    write_classic_charts()
