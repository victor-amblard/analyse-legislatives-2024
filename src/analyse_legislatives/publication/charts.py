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
from scipy.stats import norm

from analyse_legislatives.config import (
    DEFAULT_EXPECTED_EXPRESSED_CHANGE_PTS,
    DEFAULT_NATIONAL_EXPRESSED_BAND_PTS,
    DEFAULT_SEED,
    DEFAULT_TRANSFER_ORDERINGS,
    PROJECT_ROOT,
)
from analyse_legislatives.data import load_full_results, nuance_to_family
from analyse_legislatives.parties import NON_EXPRIMES, label as party_label
from analyse_legislatives.publication.sources import load_pollster_ranges
from analyse_legislatives.viz.palette import POLITICAL_FAMILY_COLORS

OUTPUT_DIR = PROJECT_ROOT / "site/public/figures"
RESULTS_DIR = PROJECT_ROOT / "artifacts/publication/models"
SENSITIVITY_DIR = PROJECT_ROOT / "artifacts/publication/sensitivity"
PRIOR_DIR = PROJECT_ROOT / "artifacts/publication/prior"

MODEL_COLOURS = {
    "National anchored": "#2a78d6",
    "Kernel anchored": "#b56824",
}

DELTA_EXAMPLE_DRAWS = 20_000
SIMPLEX_DRAWS = 20_000


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
    source = load_pollster_ranges()
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
        alt.Tooltip("party:N", title="Group"),
        alt.Tooltip("pollster:N", title="Pollster"),
        alt.Tooltip("low:Q", title="Low"),
        alt.Tooltip("high:Q", title="High"),
        alt.Tooltip("actual:Q", title="Actual"),
    ]
    ranges = (
        alt.Chart(data)
        .mark_rule(
            color="#3987e5" if dark else "#2a78d6",
            strokeWidth=5,
            strokeCap="round",
        )
        .encode(
            x=alt.X("low:Q", title="Seats", scale=alt.Scale(domain=[0, 230])),
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
        alt.Tooltip("party:N", title="Group"),
        alt.Tooltip("retained:Q", title="Final candidates"),
        alt.Tooltip("withdrawn:Q", title="Withdrawals"),
        alt.Tooltip("total:Q", title="Initially qualified"),
    ]
    retained = (
        alt.Chart(summary)
        .mark_bar(color="#68707d" if dark else "#aeb3bc", height=14)
        .encode(x=alt.X("retained:Q", title="Candidates"), y=y, tooltip=tooltip)
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
            f"{total_withdrawn} withdrawals reshaped the second round",
            subtitle=(
                "Final candidates are grey; coloured segments are withdrawals. "
                "Labels give withdrawals / initially qualified."
            ),
        ),
    )
    return _style(chart, dark=dark)


def kernel_sensitivity_chart(*, dark: bool = False) -> alt.Chart:
    data = pd.read_csv(SENSITIVITY_DIR / "kernel-h-lambda.csv")
    data = data[data["party"].isin(["NFP+", "ENS+", "RN+"])].copy()
    data["h"] = data["bandwidth_multiplier"].map(lambda value: f"×{value:g}")
    data["lambda"] = data["mixing_weight"].map(lambda value: f"λ={value:g}")
    data["reference"] = np.isclose(data["bandwidth_multiplier"], 1.0) & np.isclose(
        data["mixing_weight"], 0.5
    )

    h_order = ["×0.25", "×0.5", "×1", "×2"]
    lambda_order = ["λ=1", "λ=0.75", "λ=0.5", "λ=0.25", "λ=0"]
    base = alt.Chart(data).encode(
        x=alt.X("h:N", sort=h_order, title="Bandwidth h"),
        y=alt.Y("lambda:N", sort=lambda_order, title=None),
        tooltip=[
            alt.Tooltip("party:N", title="Group"),
            alt.Tooltip("bandwidth_multiplier:Q", title="h multiplier"),
            alt.Tooltip("mixing_weight:Q", title="λ"),
            alt.Tooltip("width90:Q", title="90% width", format=".1f"),
        ],
    )
    tiles = base.mark_rect(stroke="#ffffff", strokeWidth=0.7).encode(
        color=alt.Color(
            "width90:Q",
            title="90% interval width",
            scale=alt.Scale(scheme="blues"),
            legend=None,
        )
    )
    labels = base.mark_text(font="Arial", fontSize=10, fontWeight=600).encode(
        text=alt.Text("width90:Q", format=".0f"),
        color=alt.condition(
            "datum.width90 >= 78", alt.value("white"), alt.value("#16181d")
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
                "How dependence changes national seat uncertainty",
                subtitle=[
                    "Width of the central 90% seat interval for each fixed h and λ.",
                    "Darker means wider; the outlined cell is h×1 and λ=0.5, the prior mean.",
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
            title="Abstention + blank/null votes (% registered)",
            axis=alt.Axis(tickCount=12),
        ),
        "y": alt.Y(
            "median_seats:Q",
            title="Median seats",
            scale=alt.Scale(zero=True),
        ),
        "color": colour,
        "tooltip": [
            alt.Tooltip("parti:N", title="Group"),
            alt.Tooltip("non_expressed:Q", title="Non-expressed", format=".1f"),
            alt.Tooltip("median_seats:Q", title="Median seats", format=".1f"),
            alt.Tooltip("simulations:Q", title="Simulations", format=",d"),
        ],
    }
    line = alt.Chart(data).mark_line(strokeWidth=2).encode(**encoding)
    points = alt.Chart(data).mark_point(filled=True, size=28).encode(**encoding)
    chart = (line + points).properties(
        width=680,
        height=318,
        title=alt.Title(
            "Seats conditional on simulated abstention",
            subtitle=(
                "National anchored prior predictive, α=1; "
                "points aggregate one percentage point."
            ),
        ),
    )
    return _style(chart, dark=dark)


def alpha_sensitivity_chart(*, dark: bool = False) -> alt.Chart:
    """Prior-predictive seat intervals for fixed Dirichlet concentrations."""
    data = pd.read_csv(PRIOR_DIR / "alpha-sensitivity.csv")
    data["alpha_label"] = data["alpha"].map(lambda value: f"α={value:g}")

    parties = list(dict.fromkeys(data["parti"]))
    alpha_order = [f"α={value:g}" for value in sorted(data["alpha"].unique())]
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
            alt.Tooltip("parti:N", title="Group"),
            alt.Tooltip("alpha:Q", title="α"),
            alt.Tooltip("p05:Q", title="5%", format=".0f"),
            alt.Tooltip("mediane:Q", title="Median", format=".0f"),
            alt.Tooltip("p95:Q", title="95%", format=".0f"),
        ],
    }
    x_scale = alt.Scale(domain=[0, max(270, float(data["p95"].max()) + 15)])
    intervals = (
        alt.Chart(data)
        .mark_rule(strokeWidth=2)
        .encode(
            x=alt.X("p05:Q", title="Seats", scale=x_scale),
            x2="p95:Q",
            strokeDash=alt.StrokeDash(
                "alpha_label:N",
                sort=alpha_order,
                scale=alt.Scale(
                    domain=alpha_order,
                    range=[[4, 2], [1, 0], [4, 2]],
                ),
                legend=None,
            ),
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
            "Sensitivity to Dirichlet concentration",
            subtitle=(
                "Median and 90% prior-predictive interval; "
                "no second-round result is used."
            ),
        ),
    )
    return _style(chart, dark=dark)


def seat_results_chart(*, dark: bool = False) -> alt.Chart:
    """Marginal seat intervals for the three published model variants."""
    model_labels = {
        "national": "National",
        "national_anchored": "National anchored",
        "kernel_anchored": "Kernel anchored",
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
            alt.Tooltip("party:N", title="Group"),
            alt.Tooltip("model_label:N", title="Model"),
            alt.Tooltip("p05:Q", title="5%", format=".0f"),
            alt.Tooltip("p25:Q", title="25%", format=".0f"),
            alt.Tooltip("median:Q", title="Median", format=".0f"),
            alt.Tooltip("p75:Q", title="75%", format=".0f"),
            alt.Tooltip("p95:Q", title="95%", format=".0f"),
            alt.Tooltip("actual:Q", title="Actual", format=".0f"),
        ],
    }
    x = alt.X("p05:Q", title="Seats", scale=alt.Scale(domain=[0, 280]))
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
    actuals = (
        alt.Chart(data)
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
            yOffset=shared["yOffset"],
            tooltip=shared["tooltip"],
        )
    )
    actual_labels = (
        alt.Chart(data[data["model"].eq("national")])
        .mark_text(
            align="center",
            baseline="bottom",
            dy=-8,
            color="#e9eaee" if dark else "#16181d",
            font="Arial",
            fontSize=10,
            fontWeight=600,
        )
        .encode(
            x=alt.X("actual:Q", scale=alt.Scale(domain=[0, 280])),
            y=shared["y"],
            yOffset=alt.YOffset("model_label:N", sort=models),
            text=alt.Text("actual:Q", format=".0f"),
        )
    )
    chart = alt.layer(
        interval_90, interval_50, medians, actuals, actual_labels
    ).properties(width=650, height=76 * len(parties))
    return _style(chart, dark=dark)


def joint_region_chart(*, dark: bool = False) -> alt.Chart:
    """Position of the observed seat vector in both joint predictive laws."""
    models = {
        "national_anchored": "National anchored",
        "kernel_anchored": "Kernel anchored",
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
                    title="Joint energy score",
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
        observed_data = pd.DataFrame(
            {
                "score": [float(observed["joint_score"])],
                "label": [
                    f"actual: {float(observed['observed_percentile']):.0%} percentile"
                ],
            }
        )
        observed_rule = (
            alt.Chart(observed_data)
            .mark_rule(color=ink, strokeWidth=1.5)
            .encode(x="score:Q")
        )
        observed_label = (
            alt.Chart(observed_data)
            .mark_text(
                align="left",
                baseline="top",
                dx=5,
                dy=4,
                color=ink,
                font="Arial",
                fontSize=10,
                fontWeight=600,
            )
            .encode(x="score:Q", y=alt.value(0), text="label:N")
        )
        panels.append(
            alt.layer(
                histogram,
                threshold_rules,
                threshold_labels,
                observed_rule,
                observed_label,
            ).properties(
                width=650,
                height=112,
                title=alt.Title(label, anchor="start", fontSize=11),
            )
        )

    chart = alt.vconcat(*panels, spacing=18).properties(
        title=alt.Title(
            "Where did the actual result land jointly?",
            subtitle=(
                "Split-sample energy-score centrality; "
                "lower scores are more central under the model."
            ),
        )
    )
    return _style(chart, dark=dark).resolve_scale(x="independent", y="independent")


def _dominant_party_data() -> pd.DataFrame:
    labels = {
        "national_anchored": "National anchored",
        "kernel_anchored": "Kernel anchored",
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


TIE_LABEL = "Tie for first"
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
    data = data[data["model"] == "National anchored"]
    order = data.sort_values("probability", ascending=False)["party"].tolist()

    base = alt.Chart(data).encode(
        x=alt.X(
            "probability:Q",
            title="Probability of being the unique largest group",
            axis=alt.Axis(format="%"),
            # Domaine dérivé : un maximum écrit en dur tronque la barre dès que
            # les artefacts changent, ce qui est arrivé.
            scale=alt.Scale(
                domain=[0, min(1.0, float(data["probability"].max()) * 1.22)]
            ),
        ),
        y=alt.Y("party:N", sort=order, title=None),
        tooltip=[
            alt.Tooltip("party:N", title="Group"),
            alt.Tooltip("probability:Q", title="Probability", format=".1%"),
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
                "Distribution _prior-predictive_ de la probabilité d'avoir une majorité relative"
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
                    title=f"{x_name} seats",
                    scale=alt.Scale(domain=[x_low, x_high]),
                ),
                x2="x1:Q",
                y=alt.Y(
                    "y0:Q",
                    title=f"{y_name} seats",
                    scale=alt.Scale(domain=[y_low, y_high]),
                ),
                y2="y1:Q",
                color=alt.Color(
                    "count:Q", scale=alt.Scale(scheme="blues"), legend=None
                ),
                tooltip=[
                    alt.Tooltip("x0:Q", title=f"{x_name} from", format=".0f"),
                    alt.Tooltip("x1:Q", title="to", format=".0f"),
                    alt.Tooltip("y0:Q", title=f"{y_name} from", format=".0f"),
                    alt.Tooltip("y1:Q", title="to", format=".0f"),
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
                        "label": ["Actual 2024 result"],
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
            subtitle="Kernel anchored prior predictive; darker cells contain more simulations, diamond is the actual result.",
        )
    )
    return _style(chart, dark=dark).resolve_scale(color="independent")


def expressed_share_chart(*, dark: bool = False) -> alt.Chart:
    """Prior-predictive national expressed share under the anchored model."""
    data = pd.read_csv(RESULTS_DIR / "expressed-diagnostics-national_anchored.csv")
    data = data[data["scope"].eq("national_draw")]
    n_simulations = len(data)
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
                f"Modèle national ancré, {n_simulations:,} simulations ; bande orange : intervalle central à 90 %, "
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
    chart = (band + bars + median_rule).properties(
        width=620,
        height=225,
        title=alt.Title(
            "0101 : incertitude sur le choc national",
            subtitle=(
                f"Partie centrale à 99 % des {len(delta):,} tirages de δnat, avec δ0101 = 0 ; "
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
        "kernel_anchored": "Kernel ancré",
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
                    "Médiane prédictive moins résultat réel, en points de pourcentage. "
                    "Une erreur positive signifie une participation surestimée."
                ),
            )
        )
    )
    return _style(chart, dark=dark)


SIMPLEX_DUEL = ("LR", "RN+")
"""Duel de la circonscription 0101, utilisé comme fil rouge du billet."""

SIMPLEX_SOURCE = "ENS+"
"""Réservoir éliminé choisi pour illustrer la contrainte ordinale."""

SIMPLEX_ALPHAS = (0.5, 1.0)


def restricted_tiers(source_label=SIMPLEX_SOURCE, duel_labels=SIMPLEX_DUEL):
    """
    Paliers de préférence d'une ligne, restreints aux seules destinations
    disponibles dans ce duel : les deux qualifiés et les non-exprimés.

    C'est ce que le modèle applique réellement — `normalize_for_district` retire
    les colonnes absentes du bulletin — et ça ne coïncide pas nécessairement avec
    l'ordre complet. En 0101, la ligne ENS+ se réduit à
    `{LR} > {RN+, NON_EXPRIMES}` : RN+ et la non-expression sont EX AEQUO. La
    région compatible occupe donc un tiers du simplexe et non un sixième.
    """
    by_label = {party_label(p): p for p in DEFAULT_TRANSFER_ORDERINGS}
    duel = {by_label[label] for label in duel_labels}
    keep = duel | {NON_EXPRIMES}
    tiers = DEFAULT_TRANSFER_ORDERINGS[by_label[source_label]]
    restricted = [[t for t in tier if t in keep] for tier in tiers]
    return [tier for tier in restricted if tier]


def _simplex_draws(tiers, alpha, n=SIMPLEX_DRAWS, seed=DEFAULT_SEED):
    """
    Tirages Dirichlet(alpha) contraints par `tiers`, par le mécanisme du modèle.

    `Model.gammas_to_row` normalise des Gamma(alpha) — ce qui donne exactement une
    Dirichlet — puis affecte les parts TRIÉES le long d'une extension linéaire de
    l'ordre. Les ex aequo d'un même palier reçoivent donc leurs parts dans un
    ordre tiré au hasard, ce qui reproduit ici l'union des régions compatibles au
    lieu d'une seule chaîne stricte.
    """
    rng = np.random.default_rng(seed)
    flat = [t for tier in tiers for t in tier]
    shares = rng.gamma(alpha, 1.0, size=(n, len(flat)))
    shares /= shares.sum(axis=1, keepdims=True)
    shares = np.sort(shares, axis=1)[:, ::-1]

    out = np.empty_like(shares)
    cursor = 0
    for tier in tiers:
        width = len(tier)
        block = shares[:, cursor : cursor + width]
        if width > 1:
            order = np.argsort(rng.random((n, width)), axis=1)
            block = np.take_along_axis(block, order, axis=1)
        for offset, destination in enumerate(tier):
            out[:, flat.index(destination)] = block[:, offset]
        cursor += width
    return flat, out


def simplex_chart(*, dark: bool = False) -> alt.Chart:
    """Densité a priori sur le simplexe des trois destinations d'un duel."""
    tiers = restricted_tiers()
    flat, _ = _simplex_draws(tiers, 1.0, n=1)
    names = ["Non-expressed" if d is NON_EXPRIMES else party_label(d) for d in flat]
    apex, left, right = 0, 1, 2  # le palier de tête occupe le sommet

    vertices = np.array([[0.5, np.sqrt(3) / 2], [0.0, 0.0], [1.0, 0.0]])
    bins = 46

    ink = "#e9eaee" if dark else "#16181d"
    outline = "#555c69" if dark else "#c9cdd5"
    scheme = "darkblue" if dark else "blues"
    region_colour = "#7aa7ee" if dark else "#244f9d"

    axes = dict(axis=None, scale=alt.Scale(domain=[0, 1], nice=False))
    y_axes = dict(axis=None, scale=alt.Scale(domain=[0, np.sqrt(3) / 2], nice=False))

    triangle = pd.DataFrame(
        {
            "x": [*vertices[:, 0], vertices[0, 0]],
            "y": [*vertices[:, 1], vertices[0, 1]],
            "order": range(4),
        }
    )
    # Frontière de la région compatible : les points dont la part du palier de
    # tête domine celles du palier suivant. Avec un ex aequo c'est un
    # cerf-volant (sommet, deux milieux d'arête, centre) et non le triangle
    # qu'une chaîne strictement ordonnée découperait.
    corners = np.array(
        [
            vertices[apex],
            (vertices[apex] + vertices[left]) / 2,
            vertices.mean(axis=0),
            (vertices[apex] + vertices[right]) / 2,
            vertices[apex],
        ]
    )
    boundary_data = pd.DataFrame(
        {"x": corners[:, 0], "y": corners[:, 1], "order": range(len(corners))}
    )

    panels = []
    for alpha in SIMPLEX_ALPHAS:
        _, draws = _simplex_draws(tiers, alpha)
        points = draws @ vertices
        counts, xe, ye = np.histogram2d(
            points[:, 0],
            points[:, 1],
            bins=[bins, bins],
            range=[[0, 1], [0, np.sqrt(3) / 2]],
        )
        ix, iy = np.nonzero(counts)
        cells = pd.DataFrame(
            {
                "x": xe[ix],
                "x2": xe[ix + 1],
                "y": ye[iy],
                "y2": ye[iy + 1],
                "density": np.sqrt(counts[ix, iy] / counts.max()),
            }
        )

        density = (
            alt.Chart(cells)
            .mark_rect()
            .encode(
                x=alt.X("x:Q", title=None, **axes),
                x2="x2:Q",
                y=alt.Y("y:Q", title=None, **y_axes),
                y2="y2:Q",
                color=alt.Color(
                    "density:Q",
                    scale=alt.Scale(scheme=scheme, domain=[0, 1]),
                    legend=None,
                ),
            )
        )
        frame = (
            alt.Chart(triangle)
            .mark_line(color=outline, strokeWidth=1)
            .encode(x=alt.X("x:Q", **axes), y=alt.Y("y:Q", **y_axes), order="order:O")
        )
        edge = (
            alt.Chart(boundary_data)
            .mark_line(color=region_colour, strokeWidth=1.8)
            .encode(x=alt.X("x:Q", **axes), y=alt.Y("y:Q", **y_axes), order="order:O")
        )
        # `dx`/`dy` sont des propriétés de mark en Vega-Lite, pas des canaux : ils
        # ne peuvent pas être encodés par donnée. Une couche par sommet.
        labels = [
            alt.Chart(pd.DataFrame({"x": [vertices[i, 0]], "y": [vertices[i, 1]]}))
            .mark_text(
                color=ink,
                font="Arial",
                fontSize=10,
                fontWeight=600,
                dx=dx,
                dy=dy,
                align=align,
            )
            .encode(
                x=alt.X("x:Q", **axes),
                y=alt.Y("y:Q", **y_axes),
                text=alt.value(name),
            )
            for i, name, dx, dy, align in (
                (apex, names[apex], 0, -9, "center"),
                (left, names[left], -1, 14, "left"),
                (right, names[right], 1, 14, "right"),
            )
        ]
        panels.append(
            alt.layer(density, frame, edge, *labels).properties(
                width=205,
                height=190,
                title=alt.TitleParams(
                    f"α = {alpha:g}",
                    anchor="middle",
                    color=ink,
                    font="Arial",
                    fontSize=12,
                    fontWeight=600,
                ),
            )
        )

    tied = len(tiers) < len(flat)
    rest = (
        f"both {names[1]} and {names[2]}, which the declared order leaves tied"
        if tied
        else f"{names[1]}, itself above {names[2]}"
    )
    chart = alt.hconcat(*panels, spacing=18).properties(
        title=alt.TitleParams(
            "Same order, different transfer shapes",
            subtitle=[
                f"District 0101: {SIMPLEX_SOURCE} voters in the "
                f"{SIMPLEX_DUEL[0]}/{SIMPLEX_DUEL[1]} runoff.",
                f"{names[apex]} stays above {rest}; only α changes the dispersion.",
            ],
        )
    )
    return _style(chart, dark=dark)


def write_classic_charts(output_dir: Path = OUTPUT_DIR) -> None:
    """Export every conventional chart through Altair's official SVG backend."""
    output_dir.mkdir(parents=True, exist_ok=True)
    charts = {
        "pollster-intervals": pollster_intervals_chart,
        "withdrawals": withdrawals_chart,
        "kernel-sensitivity": kernel_sensitivity_chart,
        "seats-by-non-expressed": seats_non_expressed_chart,
        "alpha-sensitivity": alpha_sensitivity_chart,
        "seat-results": seat_results_chart,
        "joint-predictive-region": joint_region_chart,
        "dominant-party": dominant_party_chart,
        "joint-seats": joint_seats_chart,
        "expressed-share": expressed_share_chart,
        "district-0101-national-delta": district_0101_national_delta_chart,
        "district-expressed-error": district_expressed_error_chart,
        "dirichlet-simplex": simplex_chart,
    }
    for name, build_chart in charts.items():
        for suffix, dark in [("", False), ("-dark", True)]:
            path = output_dir / f"{name}{suffix}.svg"
            build_chart(dark=dark).save(path)
            print(f"wrote {path.relative_to(PROJECT_ROOT)} (Altair)")
