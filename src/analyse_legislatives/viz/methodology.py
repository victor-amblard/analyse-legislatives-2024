"""
Onglet « Méthodologie » de l'app.

C'est du texte d'interface, pas de la logique : il vivait dans `app.py`, dont il
représentait à lui seul 40 % des lignes, ce qui noyait le câblage réel de
l'application. C'est le SEUL module de `viz` qui importe Streamlit — `charts` et
`formatting` restent utilisables depuis les notebooks.

Volontairement COURT : il décrit le modèle par défaut (`national_anchored`), pas
les trois variantes ni les justifications de chaque choix. Celles-ci vivent dans
le billet, dont l'URL est ci-dessous — un onglet d'application et un article de
fond ne peuvent pas être maintenus en parallèle sans finir par se contredire.

Les valeurs numériques citées sont passées en arguments plutôt que réimportées
ici, pour qu'il soit impossible que la prose affiche une valeur différente de
celle que le modèle utilise vraiment.
"""

import pandas as pd
import streamlit as st

from analyse_legislatives.parties import DESTINATIONS, label
from analyse_legislatives.transfers import TransferMatrix
from analyse_legislatives.viz.charts import render_duel_sankey

BLOG_URL = "https://victor-amblard.gitlab.io/analyse-legislatives-2024"


def render(
    prior_matrix: TransferMatrix,
    *,
    non_expressed_retention_prior: tuple[float, float],
    qualified_demobilisation_prior: tuple[float, float],
    expected_expressed_change_pts: float,
    national_expressed_band_pts: float,
    district_expressed_band_pts: float,
    non_expressed_tilt_bounds: tuple[float, float],
    dirichlet_alpha_bounds: tuple[float, float],
    n_simus: int,
    seed: int,
) -> None:
    """`prior_matrix` résume la PRÉDICTIVE A PRIORI des taux (médianes par
    cellule) : le modèle ne contient aucun taux fixé à la main, donc la seule
    façon honnête de montrer les taux qu'il implique est de les tirer."""

    st.header("Le modèle en bref")
    st.markdown(
        "Le 2nd tour est simulé par un modèle de report de voix entre "
        "**7 familles politiques** et les **suffrages non exprimés**. Dans chaque "
        "circonscription, les voix des candidats éliminés et des non-exprimés du "
        "1er tour sont redistribuées entre les candidats encore en lice, selon des "
        "taux **tirés au sort** plutôt que fixés."
    )
    st.info(
        "Cette page décrit le modèle par défaut (`national_anchored`) et rien "
        f"d'autre. Le raisonnement complet — pourquoi chaque hypothèse, ce qu'elle "
        f"coûte, et ce que valent les résultats face aux instituts de sondage — est "
        f"dans [le billet]({BLOG_URL})."
    )
    st.caption(
        "`NON_EXPRIMES` regroupe l'abstention au sens strict, les votes blancs et "
        "les votes nuls : du point de vue du modèle — quel candidat récupère ce "
        "bulletin ? — les trois sont équivalents. Les métriques affichées comme "
        "« % de suffrages exprimés » en sont le complément."
    )

    _render_ordinal_core(dirichlet_alpha_bounds)
    _render_non_expressed(non_expressed_retention_prior, non_expressed_tilt_bounds)
    _render_demobilisation(qualified_demobilisation_prior)
    _render_anchor(
        expected_expressed_change_pts,
        national_expressed_band_pts,
        district_expressed_band_pts,
    )
    _render_prior_predictive(prior_matrix, n_simus, seed)


def _render_ordinal_core(dirichlet_alpha_bounds: tuple[float, float]) -> None:
    low, high = dirichlet_alpha_bounds
    st.subheader("Ce que le modèle déclare : un ordre, pas des taux")
    st.markdown(
        "Aucun taux de report n'est fixé. Le modèle déclare seulement, pour chaque "
        "groupe d'origine, un **ordre de préférence** entre destinations, sous forme "
        "de paliers. Pour un électeur `ENS+` :"
    )
    st.latex(
        r"\{\mathrm{DVG},\ \mathrm{DVD},\ \mathrm{LR},\ \mathrm{NFP+}\}"
        r"\ \succ\ \{\mathrm{RN+},\ \mathrm{NON\_EXPRIMES}\}"
    )
    st.markdown(
        "Les destinations d'un même palier ne sont **pas** départagées : leur ordre "
        "relatif est tiré au hasard à chaque simulation. `DIV` n'apparaît dans aucun "
        "palier — c'est un fourre-tout sans position politique — et sa part est tirée "
        "librement."
    )
    st.markdown(
        "Pour en faire des probabilités : on tire des variables "
        r"$\operatorname{Gamma}(\alpha,1)$ et on les normalise, ce qui donne une "
        "Dirichlet symétrique sur le simplexe ; les **trier** et les affecter dans "
        "l'ordre de préférence donne exactement cette loi restreinte à la portion du "
        "simplexe qui respecte l'ordre — sans rejet, et sans introduire la moindre "
        "valeur numérique."
    )
    st.latex(r"\log\alpha \sim \mathcal{U}\left(\log %g,\ \log %g\right)" % (low, high))
    st.caption(
        f"Une concentration nationale est tirée par simulation et partagée par toute "
        f"la matrice. À $\\alpha = 1$ la région compatible est échantillonnée "
        f"uniformément ; $\\alpha < 1$ favorise les reports tranchés. La borne haute "
        f"vaut {high:g}, donc le modèle penche vers des reports plus contrastés que "
        f"l'uniforme."
    )


def _render_non_expressed(
    prior: tuple[float, float], tilt_bounds: tuple[float, float]
) -> None:
    a, b = prior
    low, high = tilt_bounds
    st.subheader("Les non-exprimés du 1er tour")
    st.markdown(
        "C'est le plus gros réservoir du modèle. Sa ligne est traitée à part : une "
        "part $r$ reste non exprimée, le reste se mobilise et se répartit entre les "
        "qualifiés selon leurs scores du 1er tour élevés à la puissance $\\tau$."
    )
    st.latex(
        r"""
        \tilde{T}_{\mathrm{NE},\mathrm{NE}} = r
        \qquad
        \tilde{T}_{\mathrm{NE},q} = (1-r)\,
        \frac{\left(v_q^{(1)}\right)^{\tau}}{\sum_{q'}\left(v_{q'}^{(1)}\right)^{\tau}}
        """
    )
    st.markdown(
        f"$\\tau$ est **tiré** sur $[{low:g}, {high:g}]$ à chaque simulation : "
        f"$\\tau = 0$ donne la règle uniforme, $\\tau = 1$ la règle proportionnelle, "
        f"$\\tau < 0$ une mobilisation en faveur de l'outsider local. L'uniforme a "
        f"l'air neutre mais affirme qu'un nouvel électeur a autant de chances d'aller "
        f"au parti à 40 % qu'à celui à 12 % — une magnitude qu'on ne sait pas "
        f"défendre est tirée, pas fixée."
    )
    st.markdown(
        f"Dans le modèle **`national`**, $r$ suit un prior "
        f"$\\operatorname{{Beta}}({a:g}, {b:g})$, de moyenne {a / (a + b):.2f}. "
        f"Dans le modèle par défaut, il n'est **pas tiré** : il se déduit de l'ancre "
        f"de participation décrite plus bas."
    )


def _render_demobilisation(prior: tuple[float, float]) -> None:
    a, b = prior
    st.subheader("La démobilisation des candidats qualifiés")
    st.markdown(
        "La ligne d'un candidat qualifié n'est pas l'identité : ses électeurs du 1er "
        "tour peuvent revoter pour lui ou rejoindre les non-exprimés. Ils ne passent "
        "pas à l'adversaire — les ordres de préférence ne concernent que les "
        "réservoirs éliminés. Un taux national est tiré une fois par simulation, "
        "commun à tous les qualifiés :"
    )
    st.latex(r"d \sim \operatorname{Beta}(%g,\ %g)" % (a, b))
    st.caption(
        f"Moyenne {a / (a + b):.0%}, densité **nulle en $d = 0$** : l'absence totale "
        "de démobilisation est exclue. Un taux commun évite d'inventer une différence "
        "partisane que des résultats agrégés ne permettent pas d'identifier — mais il "
        "n'est pas sans effet sur l'issue, puisqu'il met à l'échelle la base du 1er "
        "tour sans toucher aux reports reçus."
    )


def _render_anchor(
    expected_change_pts: float, national_band_pts: float, district_band_pts: float
) -> None:
    st.subheader("L'ancre de participation")
    st.markdown(
        "C'est ce qui distingue le modèle par défaut du modèle `national`. Plutôt "
        "que de laisser la rétention des non-exprimés flotter dans son prior, on "
        "ancre la part de suffrages exprimés de chaque circonscription sur celle "
        "qu'elle a réalisée au 1er tour, sur l'échelle logit :"
    )
    st.latex(
        r"\operatorname{logit}(r_{c,2}) = \operatorname{logit}(r_{c,1})"
        r" + \delta_{\text{nat}} + \delta_c"
    )
    st.markdown(
        f"$\\delta_{{\\text{{nat}}}}$ est une dérive **nationale**, centrée sur "
        f"**{expected_change_pts:+.2f} point** de participation : c'est la variation "
        f"moyenne observée entre les deux tours des législatives de 2007, 2012, 2017 "
        f"et 2022. $\\delta_c$ est un écart local, indépendant d'une circonscription "
        f"à l'autre et de moyenne pondérée nulle."
    )
    st.markdown(
        f"Les deux incertitudes sont déclarées en **points de participation**, une "
        f"unité contestable par un lecteur, plutôt qu'en écarts-types logit : bande "
        f"à 90 % de $\\pm{national_band_pts:g}$ points au niveau national et de "
        f"$\\pm{district_band_pts:g}$ points au niveau local."
    )
    st.info(
        "La rétention des non-exprimés n'est alors plus tirée : elle est **déduite** "
        "de la comptabilité des voix, une fois la cible connue. Mobilisation de "
        "non-exprimés et démobilisation de qualifiés peuvent coexister — l'ancre "
        "n'impose que leur solde. Si une cible est physiquement inaccessible avec les "
        "réservoirs disponibles, elle est ramenée à la borne atteignable."
    )


def _render_prior_predictive(
    prior_matrix: TransferMatrix,
    n_simus: int,
    seed: int,
) -> None:
    st.subheader("Ce que l'ordre déclaré implique sur les taux")
    st.markdown(
        "Puisque le modèle ne fixe aucun taux, la seule façon de montrer les taux "
        "qu'il implique est de les **tirer**. Le tableau donne la médiane de la "
        "prédictive a priori de chaque cellule : ce ne sont pas des valeurs choisies, "
        "mais des conséquences de l'ordre déclaré."
    )
    labels = [label(d) for d in DESTINATIONS]
    st.dataframe(
        pd.DataFrame(prior_matrix.to_matrix(), index=labels, columns=labels).round(3),
        width="stretch",
    )
    st.caption(
        "Ligne = groupe source, colonne = destination. C'est un résumé cellule par "
        "cellule : la matrice des médianes ne respecte pas nécessairement l'ordre de "
        "préférence et ses lignes ne somment pas exactement à 1 — chaque TIRAGE le "
        "fait, leur médiane marginale non. Voir `scripts/analyses/prior_predictive.py` pour "
        "les intervalles complets."
    )
    st.markdown(
        f"**Simulations** : $N = {n_simus}$ tirages, seed fixée à `{seed}` pour la "
        "reproductibilité."
    )
    st.plotly_chart(
        render_duel_sankey(prior_matrix), width="stretch", key="duel_sankey"
    )
