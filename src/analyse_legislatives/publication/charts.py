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
    DEFAULT_EXPECTED_EXPRESSED_CHANGE_PTS,
    DEFAULT_NATIONAL_EXPRESSED_BAND_PTS,
    DEFAULT_SEED,
    PROJECT_ROOT,
)
from analyse_legislatives.data import load_full_results, nuance_to_family
from analyse_legislatives.parties import label as party_label
from analyse_legislatives.publication.sources import load_pollster_ranges
from analyse_legislatives.viz.palette import POLITICAL_FAMILY_COLORS

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
        for family, colour in POLITICAL_FAMILY_COLORS.items()
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
        for family, colour in POLITICAL_FAMILY_COLORS.items()
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
        for family, colour in POLITICAL_FAMILY_COLORS.items()
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
        for family, colour in POLITICAL_FAMILY_COLORS.items()
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
    """Marginal seat intervals for the three published model variants."""
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

    parties = ["NFP+", "DVG", "ENS+", "LR", "DVD", "RN+", "DIV"]
    models = list(model_labels.values())
    colours = (
        ["#35a98d", "#4c96ee", "#d58a45"] if dark else ["#1f8a70", "#2a78d6", "#b56824"]
    )
    colour = alt.Color(
        "model_label:N",
        title=None,
        sort=models,
        scale=alt.Scale(domain=models, range=colours),
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
    x = alt.X("p05:Q", title="Sièges", scale=alt.Scale(domain=[0, 280]))
    interval_90 = (
        alt.Chart(data)
        .mark_rule(strokeWidth=3, opacity=0.78, strokeCap="round")
        .encode(x=x, x2="p95:Q", **shared)
    )
    interval_50 = (
        alt.Chart(data)
        .mark_rule(strokeWidth=9, opacity=0.92, strokeCap="round")
        .encode(
            x=alt.X("p25:Q", scale=alt.Scale(domain=[0, 280])), x2="p75:Q", **shared
        )
    )
    medians = (
        alt.Chart(data)
        .mark_point(
            filled=True,
            size=55,
            stroke="#14161a" if dark else "#fbfbfc",
            strokeWidth=1,
        )
        .encode(x=alt.X("median:Q", scale=alt.Scale(domain=[0, 280])), **shared)
    )
    actual_data = data[["party", "actual"]].drop_duplicates()
    actual_tooltip = [
        alt.Tooltip("party:N", title="Groupe"),
        alt.Tooltip("actual:Q", title="Résultat réel", format=".0f"),
    ]
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
            x=alt.X("actual:Q", scale=alt.Scale(domain=[0, 280])),
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
            x=alt.X("actual:Q", scale=alt.Scale(domain=[0, 280])),
            y=shared["y"],
            text=alt.Text("actual:Q", format=".0f"),
        )
    )
    chart = alt.layer(
        interval_90, interval_50, medians, actuals, actual_labels
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
        party_label(family): hex for family, hex in POLITICAL_FAMILY_COLORS.items()
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
        colours = [
            POLITICAL_FAMILY_COLORS["LR"],
            POLITICAL_FAMILY_COLORS["RN+"],
        ]
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

    diagonal = (
        alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]}))
        .mark_line(strokeDash=[3, 3], color=muted, strokeWidth=1.3)
        .encode(x="x:Q", y="y:Q")
    )
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
    base = alt.Chart(data).encode(
        x=alt.X(
            "predit_moyen:Q",
            title="Probabilité de victoire prédite",
            axis=axis_pct_x,
            scale=alt.Scale(domain=[0, 1]),
        ),
        y=alt.Y(
            "realise:Q",
            title="Fréquence réalisée",
            axis=axis_pct,
            scale=alt.Scale(domain=[0, 1]),
        ),
    )
    tooltip = [
        alt.Tooltip("predit_min:Q", title="Prédit, borne basse", format=".0%"),
        alt.Tooltip("predit_max:Q", title="Prédit, borne haute", format=".0%"),
        alt.Tooltip("realise:Q", title="Réalisé", format=".1%"),
        alt.Tooltip("ic95_bas:Q", title="IC 95 %, bas", format=".1%"),
        alt.Tooltip("ic95_haut:Q", title="IC 95 %, haut", format=".1%"),
        alt.Tooltip("n:Q", title="Cellules dans la tranche"),
    ]
    error_bars = base.mark_rule(color=accent, strokeWidth=1.4, opacity=0.55).encode(
        y="ic95_bas:Q", y2="ic95_haut:Q", tooltip=tooltip
    )
    points = base.mark_circle(color=accent, opacity=0.92).encode(
        size=alt.Size(
            "n:Q",
            title="Cellules",
            scale=alt.Scale(range=[40, 420]),
            legend=alt.Legend(symbolFillColor=accent, format="d"),
        ),
        tooltip=tooltip,
    )
    chart = (diagonal + error_bars + points).properties(
        width=420,
        height=420,
        title={
            "text": "Calibration des probabilités de victoire locale",
            "subtitle": [
                f"Modèle {model} · circonscriptions et partis qualifiés,",
                "déciles à effectif égal, IC 95 % de Wilson par tranche",
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
    }
    for name, build_chart in charts.items():
        for suffix, dark in [("", False), ("-dark", True)]:
            path = output_dir / f"{name}{suffix}.svg"
            build_chart(dark=dark).save(path)
            print(f"wrote {path.relative_to(PROJECT_ROOT)} (Altair)")


if __name__ == "__main__":
    write_classic_charts()
