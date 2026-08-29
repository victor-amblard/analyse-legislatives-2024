"""
Construction des graphiques (Altair et Plotly).

Ces fonctions ne font que produire des objets graphiques à partir de
DataFrames : aucune dépendance à Streamlit, pour rester testables et
réutilisables depuis les notebooks. L'app se contente de les afficher.
"""

from collections.abc import Mapping
import altair as alt
import numpy as np
import pandas as pd
import polars as pl
import plotly.graph_objects as go

from analyse_legislatives.circonscription import Circonscription, CirconscriptionResult
from analyse_legislatives.models import NON_EXPRESSED_TILT_MIDPOINT
from analyse_legislatives.parties import (
    NON_EXPRIMES,
    DESTINATIONS,
    SPECTRUM_LABELS,
    PoliticalFamily,
    label,
)
from analyse_legislatives.transfers import TransferMatrix, normalize_for_district
from analyse_legislatives.viz.palette import POLITICAL_FAMILY_COLORS, color_for


def bin_series(series: pl.Series, n_bins: int = 30) -> pd.DataFrame:
    """
    Découpe une série en `n_bins` intervalles réguliers et renvoie le nombre
    d'observations par intervalle (colonnes bin_low / bin_high / size).

    Le binning est fait ici en pandas plutôt que délégué à Altair (`alt.Bin`)
    pour que les bornes des intervalles existent aussi côté serveur : elles sont
    renvoyées telles quelles par la sélection Streamlit quand l'utilisateur
    clique une barre, ce qui permet de retrouver les simulations concernées.
    """
    lo, hi = float(series.min()), float(series.max())
    edges = np.linspace(lo, hi, n_bins + 1)
    bin_idx = np.clip(np.digitize(series, edges[1:-1], right=False), 0, n_bins - 1)
    binned = pd.DataFrame({"bin_low": edges[bin_idx], "bin_high": edges[bin_idx + 1]})
    return binned.groupby(["bin_low", "bin_high"], as_index=False).size()


def render_expressed_share_chart(
    binned_df: pd.DataFrame, title: str, selection: alt.Parameter
):
    """Histogramme des suffrages exprimés nationaux, cliquable (la barre
    sélectionnée reste colorée, les autres sont grisées)."""
    return (
        alt.Chart(binned_df)
        .mark_bar()
        .encode(
            x=alt.X(
                "bin_low:Q",
                title="Taux de suffrages exprimés national simulé (% inscrits, 2nd tour)",
            ),
            x2="bin_high:Q",
            y=alt.Y("size:Q", title="Nombre de simulations"),
            color=alt.condition(selection, alt.value("#4C78A8"), alt.value("#bbbbbb")),
            tooltip=[
                alt.Tooltip("bin_low:Q", title="De (%)", format=".1f"),
                alt.Tooltip("bin_high:Q", title="À (%)", format=".1f"),
                alt.Tooltip("size:Q", title="Simulations"),
            ],
        )
        .add_params(selection)
        .properties(height=220, title=title)
    )


def render_district_wins_vs_non_expressed_chart(
    conditional_df: pl.DataFrame, title: str
) -> alt.Chart:
    """Probabilité de victoire par tranche d'un point de non-exprimés.

    Échelle Y forcée sur 0-100 : une courbe plate doit se LIRE comme plate. Un
    axe qui s'ajuste aux données ferait passer une variation de deux points pour
    un basculement, alors que la participation n'a d'effet marqué que dans un
    quart des circonscriptions."""
    parties = conditional_df["parti"].unique().to_list()
    domain = [p for p in SPECTRUM_LABELS if p in parties]
    colors = [color_for(PoliticalFamily(party)) for party in domain]
    return (
        alt.Chart(conditional_df)
        .mark_line(point=alt.OverlayMarkDef(size=55), strokeWidth=2)
        .encode(
            x=alt.X(
                "non_exprimés:Q",
                title="Non-exprimés simulés dans la circonscription (% des inscrits)",
                scale=alt.Scale(zero=False),
            ),
            y=alt.Y(
                "probabilite:Q",
                title="Probabilité de victoire (%)",
                scale=alt.Scale(domain=[0, 100]),
            ),
            color=alt.Color(
                "parti:N",
                title="Parti",
                scale=alt.Scale(domain=domain, range=colors),
                sort=domain,
            ),
            tooltip=[
                alt.Tooltip("parti:N", title="Parti"),
                alt.Tooltip("tranche_basse:Q", title="De (%)", format=".0f"),
                alt.Tooltip("probabilite:Q", title="Victoires", format=".0f"),
                alt.Tooltip("simulations:Q", title="Simulations", format=".0f"),
            ],
        )
        .properties(height=320, title=title)
    )


def render_seats_vs_non_expressed_chart(conditional_df: pl.DataFrame) -> alt.Chart:
    """Courbes des sièges médians par tranche d'un point de non-exprimés."""
    domain = list(SPECTRUM_LABELS)
    colors = [color_for(PoliticalFamily(party)) for party in domain]
    return (
        alt.Chart(conditional_df)
        .mark_line(point=alt.OverlayMarkDef(size=55), strokeWidth=2)
        .encode(
            x=alt.X(
                "non_exprimés:Q",
                title="Non-exprimés simulés (% des inscrits, 2nd tour)",
                scale=alt.Scale(zero=False),
            ),
            y=alt.Y(
                "sieges_medians:Q",
                title="Nombre médian de sièges",
                scale=alt.Scale(zero=False),
            ),
            color=alt.Color(
                "parti:N",
                title="Parti",
                scale=alt.Scale(domain=domain, range=colors),
                sort=domain,
            ),
            tooltip=[
                alt.Tooltip("parti:N", title="Parti"),
                alt.Tooltip("tranche_basse:Q", title="De (%)", format=".0f"),
                alt.Tooltip("tranche_haute:Q", title="À (%)", format=".0f"),
                alt.Tooltip("sieges_medians:Q", title="Sièges médians", format=".0f"),
                alt.Tooltip("p05:Q", title="Sièges, p05", format=".0f"),
                alt.Tooltip("p95:Q", title="Sièges, p95", format=".0f"),
                alt.Tooltip("simulations:Q", title="Simulations", format=".0f"),
            ],
        )
        .properties(
            height=420,
            title="Sièges médians par point de non-exprimés",
        )
        .interactive()
    )


def _nice_step(range_val: float, target_lines: int = 5) -> float:
    """Pas de graduation "rond" (1/2/5 x une puissance de 10) donnant environ
    target_lines graduations sur l'étendue range_val — même logique que les
    générateurs d'axes standards (ex. D3)."""
    if range_val <= 0:
        return 1.0
    raw_step = range_val / target_lines
    magnitude = 10 ** np.floor(np.log10(raw_step))
    for m in (1, 2, 5, 10):
        if m * magnitude >= raw_step:
            return m * magnitude
    return 10 * magnitude


def _clip_line_to_box(x0, y0, slope, domain_x, domain_y):
    """Intersecte la droite passant par (x0, y0) de pente `slope` avec le
    rectangle [domain_x] x [domain_y], et renvoie ses deux points d'entrée/sortie
    (ou None si la droite ne traverse pas le rectangle)."""
    candidates = []
    for x_edge in domain_x:
        y = y0 + slope * (x_edge - x0)
        if domain_y[0] - 1e-9 <= y <= domain_y[1] + 1e-9:
            candidates.append((x_edge, y))
    if slope != 0:
        for y_edge in domain_y:
            x = x0 + (y_edge - y0) / slope
            if domain_x[0] - 1e-9 <= x <= domain_x[1] + 1e-9:
                candidates.append((x, y_edge))
    uniq = []
    for p in candidates:
        if not any(abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9 for q in uniq):
            uniq.append(p)
    if len(uniq) < 2:
        return None
    # Les deux points les plus éloignés (au cas où un coin donnerait 3 candidats)
    return max(
        ((a, b) for i, a in enumerate(uniq) for b in uniq[i + 1 :]),
        key=lambda ab: (ab[0][0] - ab[1][0]) ** 2 + (ab[0][1] - ab[1][1]) ** 2,
    )


def render_ternary_chart(
    circo_df_with_abs: pl.DataFrame,
    party_left: str,
    party_right: str,
    title: str,
):
    """
    Diagramme ternaire : chaque simulation est un point positionné selon ses parts
    relatives entre party_left, party_right et l'abstention (les 3 sommets du
    triangle complet, qui somment à 100%). Remplace en un seul graphique ce qui
    prenait trois vues séparées (nuage 2D parti-contre-parti, écart-vs-abstention,
    histogramme d'abstention).

    La vue est zoomée sur la zone réellement peuplée par les simulations (il est
    très improbable qu'un parti ou l'abstention dépasse 75%, donc le triangle
    complet laisserait un nuage minuscule au milieu d'un espace vide) : le sommet
    du triangle complet ne rentre donc pas dans le cadre, remplacé par des
    étiquettes directionnelles en bord de zone. Le losange noir est le barycentre
    (profil moyen) des simulations.
    """
    pandas_frame = pd.DataFrame(circo_df_with_abs.to_dicts())
    wide = (
        pandas_frame[
            pandas_frame["party"].isin([party_left, party_right, NON_EXPRIMES])
        ]
        .pivot(index="id_simu", columns="party", values="votes")
        .reset_index()
    )
    total = wide[party_left] + wide[party_right] + wide[NON_EXPRIMES]
    p_right = wide[party_right] / total
    p_abs = wide[NON_EXPRIMES] / total

    sqrt3_2 = float(np.sqrt(3) / 2)
    wide["tx"] = p_right + 0.5 * p_abs
    wide["ty"] = p_abs * sqrt3_2
    wide["side"] = np.where(
        wide[party_left] > wide[party_right], party_left, party_right
    )

    pad_x = max((wide["tx"].max() - wide["tx"].min()) * 0.3, 0.03)
    pad_y = max((wide["ty"].max() - wide["ty"].min()) * 0.3, 0.03)
    domain_x = [float(wide["tx"].min() - pad_x), float(wide["tx"].max() + pad_x)]
    domain_y = [
        float(max(wide["ty"].min() - pad_y, -0.02)),
        float(wide["ty"].max() + pad_y),
    ]
    mid_x, mid_y = (domain_x[0] + domain_x[1]) / 2, (domain_y[0] + domain_y[1]) / 2

    def xy_encoding():
        return dict(
            x=alt.X("x:Q", axis=None, scale=alt.Scale(domain=domain_x)),
            y=alt.Y("y:Q", axis=None, scale=alt.Scale(domain=domain_y)),
        )

    # Graduations : une famille de lignes par sommet (% abstention = horizontales,
    # % party_right et % party_left = obliques à ±racine(3)), avec un pas "rond"
    # choisi automatiquement pour ~5 graduations visibles, coupées au cadre zoomé.
    def gridline_family(kind: str):
        if kind == "abs":
            pct_lo, pct_hi = domain_y[0] / sqrt3_2 * 100, domain_y[1] / sqrt3_2 * 100
        else:
            pcts = []
            for cx in domain_x:
                for cy in domain_y:
                    p_ab = cy / sqrt3_2
                    pcts.append(
                        (cx - 0.5 * p_ab) * 100
                        if kind == "right"
                        else (1 - cx - 0.5 * p_ab) * 100
                    )
            pct_lo, pct_hi = min(pcts), max(pcts)

        step = _nice_step(pct_hi - pct_lo)
        ticks = np.arange(np.ceil(pct_lo / step) * step, pct_hi, step)

        segments, labels = [], []
        for pct in ticks:
            if kind == "abs":
                y = pct / 100 * sqrt3_2
                seg = (domain_x[0], y, domain_x[1], y)
            else:
                slope = (1 if kind == "right" else -1) * np.sqrt(3)
                x0 = pct / 100 if kind == "right" else 1 - pct / 100
                clipped = _clip_line_to_box(x0, 0, slope, domain_x, domain_y)
                if clipped is None:
                    continue
                (ax, ay), (bx, by) = clipped
                seg = (ax, ay, bx, by)
            segments.append({"x": seg[0], "y": seg[1], "x2": seg[2], "y2": seg[3]})
            lx, ly = (seg[0], seg[1]) if seg[1] <= seg[3] else (seg[2], seg[3])
            labels.append({"x": lx, "y": ly, "text": f"{pct:.0f}%"})
        return segments, labels

    grid_segments, grid_labels = [], []
    for kind in ("abs", "right", "left"):
        segs, labs = gridline_family(kind)
        grid_segments += segs
        grid_labels += labs

    gridlines = (
        alt.Chart(pd.DataFrame(grid_segments))
        .mark_rule(color="#dddddd", strokeWidth=1)
        .encode(x2="x2:Q", y2="y2:Q", **xy_encoding())
    )
    gridline_text = (
        alt.Chart(pd.DataFrame(grid_labels))
        .mark_text(fontSize=9, color="#999999", dx=4, dy=-3)
        .encode(text="text:N", **xy_encoding())
    )
    tie_line = (
        alt.Chart(pd.DataFrame({"x": [0.5, 0.5], "y": domain_y}))
        .mark_line(color="black", strokeDash=[4, 4])
        .encode(**xy_encoding())
    )

    def edge_label(x, y, text, align, color="black"):
        return (
            alt.Chart(pd.DataFrame({"x": [x], "y": [y]}))
            .mark_text(align=align, fontSize=12, fontWeight="bold", color=color)
            .encode(text=alt.value(text), **xy_encoding())
        )

    direction_labels = (
        edge_label(
            domain_x[0],
            mid_y,
            f"◄ plus {party_left}",
            "left",
            POLITICAL_FAMILY_COLORS[party_left],
        )
        + edge_label(
            domain_x[1],
            mid_y,
            f"plus {party_right} ►",
            "right",
            POLITICAL_FAMILY_COLORS[party_right],
        )
        + edge_label(mid_x, domain_y[1], "▲ plus de non-exprimés", "center")
    )

    points = (
        alt.Chart(wide)
        .mark_circle(size=25, opacity=0.35)
        .encode(
            x=alt.X("tx:Q", axis=None, scale=alt.Scale(domain=domain_x)),
            y=alt.Y("ty:Q", axis=None, scale=alt.Scale(domain=domain_y)),
            color=alt.Color(
                "side:N",
                scale=alt.Scale(
                    domain=[party_left, party_right],
                    range=[
                        POLITICAL_FAMILY_COLORS[party_left],
                        POLITICAL_FAMILY_COLORS[party_right],
                    ],
                ),
                legend=alt.Legend(title="Vainqueur"),
            ),
            tooltip=[
                alt.Tooltip(f"{party_left}:Q", title=f"Voix {party_left}"),
                alt.Tooltip(f"{party_right}:Q", title=f"Voix {party_right}"),
                alt.Tooltip(f"{NON_EXPRIMES}:Q", title="Non exprimé"),
            ],
        )
    )

    barycenter_df = pd.DataFrame(
        {
            "x": [wide["tx"].mean()],
            "y": [wide["ty"].mean()],
            f"{party_left} (%)": [
                round(float((wide[party_left] / total).mean() * 100), 1)
            ],
            f"{party_right} (%)": [
                round(float((wide[party_right] / total).mean() * 100), 1)
            ],
            "Non exprimé (%)": [round(float(p_abs.mean() * 100), 1)],
        }
    )
    barycenter = (
        alt.Chart(barycenter_df)
        .mark_point(
            shape="diamond",
            size=200,
            filled=True,
            color="black",
            stroke="white",
            strokeWidth=1.5,
        )
        .encode(
            tooltip=[f"{party_left} (%)", f"{party_right} (%)", "Non exprimé (%)"],
            **xy_encoding(),
        )
    )

    return (
        (gridlines + gridline_text + tie_line + points + barycenter + direction_labels)
        .properties(width=480, height=440, title=title)
        .configure_view(strokeWidth=0)
    )


def render_margin_chart(
    circo_df_with_abs: pl.DataFrame,
    party_a: str,
    party_b: str,
    title: str,
    maxbins: int = 40,
):
    """
    Distribution de l'écart de voix (party_a − party_b) sur les simulations,
    colorée par vainqueur, avec la ligne d'égalité en pointillés. Cliquer une
    barre met en évidence l'intervalle correspondant (double-clic pour annuler).
    """
    pandas_frame = pd.DataFrame(circo_df_with_abs.to_dicts())
    wide = pandas_frame.pivot(
        index="id_simu", columns="party", values="votes"
    ).reset_index()
    wide["margin"] = wide[party_a] - wide[party_b]
    wide["side"] = np.where(wide["margin"] > 0, party_a, party_b)

    click = alt.selection_point(
        encodings=["x"], on="click", clear="dblclick", empty=True
    )
    margin_bars = (
        alt.Chart(wide)
        .mark_bar()
        .encode(
            x=alt.X(
                "margin:Q",
                title=f"Écart de voix ({party_a} − {party_b})",
                bin=alt.Bin(maxbins=maxbins),
            ),
            y=alt.Y("count():Q", title="Nombre de simulations"),
            color=alt.condition(
                click,
                alt.Color(
                    "side:N",
                    scale=alt.Scale(
                        domain=[party_a, party_b],
                        range=[
                            POLITICAL_FAMILY_COLORS[party_a],
                            POLITICAL_FAMILY_COLORS[party_b],
                        ],
                    ),
                    legend=None,
                ),
                alt.value("#dddddd"),
            ),
            tooltip=[alt.Tooltip("count():Q", title="Simulations")],
        )
        .add_params(click)
    )
    zero_line = (
        alt.Chart(pd.DataFrame({"x": [0]}))
        .mark_rule(color="black", strokeDash=[4, 4])
        .encode(x="x:Q")
    )
    return (margin_bars + zero_line).properties(height=220, title=title)


def hemicycle_positions(
    seats_per_party: Mapping[str, int], n_rows: int = 10
) -> pd.DataFrame:
    """
    Place chaque siège sur des arcs concentriques semi-circulaires (diagramme
    "hémicycle" classique), en répartissant les rangées de façon à garder un
    espacement à peu près constant entre sièges adjacents (plus de sièges sur les
    arcs extérieurs, plus longs).

    Chaque parti occupe une tranche angulaire contiguë, comme un camembert déplié
    en demi-cercle (angle = pi à gauche, 0 à droite ; % de sièges -> % de l'angle
    total). Un siège est attribué au parti dont la tranche contient son angle —
    PAS en triant les points par coordonnée x, qui dépend aussi du rayon et
    déformerait les frontières entre partis d'un arc à l'autre.
    """
    n_seats = int(sum(seats_per_party.values()))
    if n_seats == 0:
        return pd.DataFrame(columns=["x", "y", "party"])

    angle_bounds = {}  # party -> (angle_max, angle_min), de gauche (pi) à droite (0)
    cumulative = 0
    for party in SPECTRUM_LABELS:
        angle_max = np.pi * (1 - cumulative / n_seats)
        cumulative += seats_per_party.get(party, 0)
        angle_min = np.pi * (1 - cumulative / n_seats)
        angle_bounds[party] = (angle_max, angle_min)

    def party_for_angle(theta: float) -> str:
        for party, (angle_max, angle_min) in angle_bounds.items():
            if angle_min - 1e-9 <= theta <= angle_max + 1e-9:
                return party
        return SPECTRUM_LABELS[-1]  # filet de sécurité (arrondi flottant)

    weights = np.arange(1, n_rows + 1)
    seats_per_row = np.round(weights / weights.sum() * n_seats).astype(int)
    seats_per_row[-1] += n_seats - seats_per_row.sum()  # absorbe l'écart d'arrondi

    r_min, r_max = 3.0, 10.0
    xs, ys, parties = [], [], []
    for i, n_in_row in enumerate(seats_per_row):
        if n_in_row <= 0:
            continue
        r = r_min + (r_max - r_min) * i / max(n_rows - 1, 1)
        angles = (
            np.linspace(0, np.pi, n_in_row) if n_in_row > 1 else np.array([np.pi / 2])
        )
        for a in angles:
            xs.append(r * np.cos(a))
            ys.append(r * np.sin(a))
            parties.append(party_for_angle(a))

    return pd.DataFrame({"x": xs, "y": ys, "party": parties})


def render_hemicycle(seats_per_party: Mapping[str, int]):
    return (
        alt.Chart(hemicycle_positions(seats_per_party))
        .mark_circle(size=120)
        .encode(
            x=alt.X("x:Q", axis=None, scale=alt.Scale(domain=[-11, 11])),
            y=alt.Y("y:Q", axis=None, scale=alt.Scale(domain=[-0.5, 10.5])),
            color=alt.Color(
                "party:N",
                scale=alt.Scale(
                    domain=SPECTRUM_LABELS,
                    range=[color_for(p) for p in SPECTRUM_LABELS],
                ),
                legend=alt.Legend(title="Parti"),
            ),
            tooltip=["party:N"],
        )
        .properties(width=760, height=400)
        .configure_view(strokeWidth=0)
    )


def _hex_to_rgba(hex_color: str, alpha: float = 0.45) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def render_duel_sankey(
    hyperparameters: TransferMatrix,
    party_a=PoliticalFamily.NFPx,
    party_b=PoliticalFamily.RNx,
) -> go.Figure:
    """
    Exemple concret plutôt que la matrice brute abstraite : pour un duel
    party_a vs party_b, montre comment les électeurs des partis éliminés (et les
    non-exprimés du 1er tour) se répartissent réellement entre les deux qualifiés, une
    fois la normalisation par circonscription appliquée (voir
    `transfers.normalize_for_district`) — party_a/party_b gardent directement
    leurs voix du 1er tour, donc n'apparaissent qu'en cible, jamais en source.
    """
    example_competing = {
        destination: (1 if destination in (party_a, party_b) else 0)
        for destination in DESTINATIONS
    }
    example_district = CirconscriptionResult(
        Circonscription("EX", "Exemple"), example_competing, {}, 0
    )
    # Milieu du prior : ce graphique illustre une matrice, il ne simule rien.
    normalized = normalize_for_district(
        hyperparameters, example_district, NON_EXPRESSED_TILT_MIDPOINT
    )

    sources_order = [p for p in DESTINATIONS if p not in (party_a, party_b)]
    targets_order = [party_a, party_b, NON_EXPRIMES]

    src_idx = {p: i for i, p in enumerate(sources_order)}
    tgt_idx = {p: len(sources_order) + i for i, p in enumerate(targets_order)}
    labels = [label(p) for p in sources_order + targets_order]
    colors = [color_for(p) for p in sources_order + targets_order]

    sources, targets, values, link_colors = [], [], [], []
    for sp in sources_order:
        for tp in targets_order:
            rate = normalized.rates.get(sp, {}).get(tp, 0)
            if rate > 1e-6:
                sources.append(src_idx[sp])
                targets.append(tgt_idx[tp])
                values.append(rate)
                link_colors.append(_hex_to_rgba(colors[src_idx[sp]]))

    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(
                    label=labels,
                    color=colors,
                    pad=30,
                    thickness=20,
                    line=dict(color="white", width=0.5),
                ),
                link=dict(
                    source=sources, target=targets, value=values, color=link_colors
                ),
            )
        ]
    )
    fig.update_layout(
        title_text=(
            f"Exemple — duel {label(party_a)} / {label(party_b)} : "
            "où vont les voix des partis éliminés et des non-exprimés du 1er tour ?"
        ),
        font_size=12,
        height=520,
    )
    return fig


TIE_LABEL = "Égalité"
"""Les scénarios où deux groupes arrivent premiers ex aequo sont comptés à part
plutôt que départagés arbitrairement par `argmax`, qui trancherait selon l'ordre
des colonnes — un artefact d'implémentation, pas un résultat."""


def render_dominant_party_chart(
    seats_by_simulation: pl.DataFrame, parties=("NFP+", "ENS+", "RN+")
) -> alt.Chart:
    """
    Probabilité prédictive d'être l'unique premier groupe en sièges.

    Calculée sur les simulations de l'app elle-même, et non lue dans un artefact
    figé : les autres onglets affichent les mêmes tirages, et deux sources
    différentes finiraient par se contredire au premier changement de graine ou
    d'hyperparamètre.

    Une seule série, donc la couleur est libre d'identifier le GROUPE — c'est la
    comparaison utile ici. L'égalité, qui n'est pas un groupe, garde un gris
    neutre.
    """
    values = seats_by_simulation.select(SPECTRUM_LABELS).to_numpy()
    maxima = values.max(axis=1)
    tied = (values == maxima[:, None]).sum(axis=1) > 1
    winners = np.asarray(SPECTRUM_LABELS, dtype=object)[values.argmax(axis=1)]
    winners = np.where(tied, TIE_LABEL, winners)

    data = pd.DataFrame(
        {
            "groupe": [*parties, TIE_LABEL],
            "probabilite": [
                float(np.mean(winners == party)) for party in (*parties, TIE_LABEL)
            ],
        }
    )
    colours = {party: color_for(party) for party in parties}
    colours[TIE_LABEL] = "#8a9099"
    order = data.sort_values("probabilite", ascending=False)["groupe"].tolist()

    base = alt.Chart(data).encode(
        x=alt.X(
            "probabilite:Q",
            title="Probabilité d'être seul premier groupe",
            axis=alt.Axis(format="%"),
            scale=alt.Scale(
                domain=[0, min(1.0, float(data["probabilite"].max()) * 1.22)]
            ),
        ),
        y=alt.Y("groupe:N", sort=order, title=None),
        tooltip=[
            alt.Tooltip("groupe:N", title="Groupe"),
            alt.Tooltip("probabilite:Q", title="Probabilité", format=".1%"),
        ],
    )
    bars = base.mark_bar(height=18, cornerRadiusEnd=3).encode(
        color=alt.Color(
            "groupe:N",
            scale=alt.Scale(domain=list(colours), range=list(colours.values())),
            legend=None,
        )
    )
    labels = base.mark_text(
        align="left", baseline="middle", dx=6, fontWeight=600
    ).encode(text=alt.Text("probabilite:Q", format=".1%"))
    return (bars + labels).properties(height=alt.Step(30)).configure_view(strokeWidth=0)
