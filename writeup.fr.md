---
title: "Un modèle de prévision électorale sans sondage ni données historiques"
description: "Juste avant les législatives de 2024, j'ai consacré quelques jours à construire un modèle de prévision simple. Voici comment, et pourquoi la simplicité peut parfois valoir mieux que des sondages coûteux."
date: 2026-09-07
author: Victor Amblard
lang: fr
---

# Pouvait-on prévoir le second tour des législatives sans sondage ni données historiques ?

_Les intentions déclarées prédisent-elles les votes réels ?
Les comportements observés lors d'élections précédentes restent-ils valables aux élections suivantes ? Ces deux hypothèses sont au cœur de nombreuses projections électorales aujourd'hui._

_Peut-on néanmoins construire une prévision crédible des résultats des élections législatives sans ces deux hypothèses fortes ?_

_Entre les deux tours des élections législatives de 2024, j'ai consacré quelques jours à construire un modèle statistique simple de prévision du second tour (amélioré par la suite, tout en essayant de ne pas être biaisé par les résultats du 2nd tour). Il repose sur les résultats du premier tour et la liste des candidats au second : peu d'hypothèses politiques explicites, aucun sondage, aucun résultat passé et des résultats satisfaisants : 450 des 501 circonscriptions sont correctement prédites._

_Ce billet propose une plongée pédagogique dans la construction du modèle, la méthodologie utilisée, ses résultats et ses limites. Pour les plus curieux, les détails mathématiques se trouvent dans des encadrés dépliants._

Tout le code des modèles et des expériences est disponible [sur GitHub](https://github.com/victor-amblard/analyse-legislatives-2024) et les prévisions interactives [ici](https://legislatives2024.vicstorm.ovh/).

> Note : Ce projet a avant tout une visée pédagogique pour illustrer un cas d'usage de modèle statistique de prévision. Le modèle a été révisé après les résultats du second tour, non pas pour en utiliser les résultats mais pour l'affiner avec davantage de temps.


## Introduction

### La réalité des sondages politiques

À l'approche d'une élection, les sondages politiques et projections saturent l'espace médiatique. Les sondages d'opinion, encadrés par la loi, reposent souvent sur des enquêtes réalisées auprès d'un échantillon _représentatif_ de quelques centaines à quelques milliers de personnes interrogées sur leurs intentions de vote[^1].
[^1]: La définition issue de la loi du 19 juillet 1977 est la suivante "_une enquête statistique visant à donner une indication quantitative, à une date déterminée, des opinions, souhaits, attitudes ou comportements d'une population par l'interrogation d'un échantillon._"

Les résultats peuvent être publiés tels quels ou intégrés à des projections (en sièges ou en pourcentage), souvent accompagnées de _marges d'erreur_[^2] qui découlent souvent de la combinaison de sondages et de modèles statistiques.
[^2]: Ces marges d'erreur sont parfois aussi appelées "intervalles de confiance" par les instituts.

Entre les deux tours des élections législatives de 2024, j'ai été frappé par l'étroitesse des marges d'erreur publiées. Sur l'illustration ci-dessous, on peut constater qu'aucune des quatre dernières projections publiées quelques jours avant le second tour ne contient le résultat du RN et alliés au niveau national.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/pollster-intervals-dark.svg" />
  <img src="/figures/pollster-intervals.svg"
       alt="Fourchettes de sièges publiées par quatre instituts avant les législatives de 2024, avec le résultat observé indiqué pour chaque groupe." />
  </picture>
  <figcaption>
    Chaque ligne correspond à la fourchette publiée par un institut ; le losange
    indique le résultat réel des élections. Lorsqu'une fourchette manque ce résultat, le
    trait pointillé mesure l'écart. <strong>Les quatre projections ont surestimé
    RN+ de 28 à 43 sièges.</strong> Source : données adaptées de
    <a href="https://fr.wikipedia.org/wiki/Liste_de_sondages_sur_les_%C3%A9lections_l%C3%A9gislatives_fran%C3%A7aises_de_2024">Wikipédia</a>.
  </figcaption>
</figure>

Bien entendu, une seule élection ne suffit pas à conclure. Le cas n'est toutefois pas isolé : aux législatives de 2022, le nombre de sièges de la NUPES s'est également trouvé hors de plusieurs fourchettes publiées.

À mon sens, le problème n'est pas qu'une prévision puisse se tromper mais que des marges d'erreur trop étroites donnent une fausse impression de confiance dans ces prévisions, ensuite abondamment reprises sur les plateaux télévisés. Elles devraient représenter ce que le modèle statistique n'arrive pas à prévoir des comportements humains, mais parfois trop d'information qui se révèle _a posteriori_ erronée est incorporée dans ces modèles : les intentions déclarées ne prédisent pas correctement le comportement électoral effectif...

### Mieux vaut être incertain que faussement précis

J'ai souhaité construire un modèle statistique simple qui ne repose pas sur ce que les personnes déclarent mais sur la manière dont ces personnes ont agi. Et plus précisément sur la manière dont ces personnes ont agi _récemment_. Pas de sondage. Pas de données historiques.

Le défi principal était de ne formuler aucune hypothèse que je ne sache défendre, de laisser le modèle s'adapter aux données du premier tour et de tirer au hasard tout ce sur quoi je n'ai pas d'avis, quitte à être relativement incertain.

> **Avertissement**
>
> Ce billet décrit un projet personnel et ne prétend pas proposer une méthode générale de prévision électorale.

### Prédire des élections législatives, un exercice complexe ?

La prédiction des résultats du second tour des élections législatives est un problème complexe pour plusieurs raisons :

- d'abord, la nature _locale_ des élections : avec un siège par circonscription, les erreurs locales ne s'annulent pas nécessairement à l'échelle nationale, contrairement à celles d'une élection présidentielle ;
- l'abstention est plus élevée qu'aux élections présidentielles et les non-exprimés constituent même le plus gros réservoir de voix au moment du second tour ;
- des mécanismes de désistement peuvent avoir lieu dans certaines circonscriptions initialement configurées en triangulaires ou quadrangulaires. Le comportement des électeurs des candidats qui se désistent est complexe.

### Un contexte politique particulier en 2024

#### Une alliance des partis de gauche

Une des spécificités des élections législatives de 2024 a été l'alliance de plusieurs partis de gauche appelée "Nouveau Front Populaire" (NFP), parfois aussi appelée "Union de la gauche". Pour simplifier l'analyse, j'ai regroupé certaines nuances par affinités afin de ne conserver que les principales forces politiques en jeu, regroupées sous 7 catégories : `NFP+`, `DVG`, `ENS+`, `LR`, `DVD`, `RN+` et `DIV`.


<details>
<summary>Tableau de correspondance entre codes officiels et notations du post</summary>

Le tableau suivant donne la correspondance entre les notations utilisées par la suite et les codes officiels du ministère de l'Intérieur.

| Notation | Étiquettes Min. Intérieur |
| --- | --- |
| NFP+ | UG, FI, ECO, SOC, RDG, VEC, COM, EXG |
| ENS+ | ENS, HOR, UDI, MDM, DVC |
| DVG | DVG |
| LR | LR |
| DVD | DVD |
| RN+ | RN, UXD, DSV, REC |
| DIV | DIV, REG |

Avec ces conventions, les résultats officiels sont les suivants :
<figure>

Sur 577 circonscriptions, 76 ont été pourvues dès le premier tour

| Tour | NFP+ | DVG | ENS+ | LR | DVD | RN+ | DIV | _Total_ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1er tour | 32 | 0 | 2 | 1 | 2 | 39 | 0 | _76_ |
| 2e tour | 149 | 12  | 163 | 38 | 25 | 104 | 10 | _501_ |
| Total | 181 | 12 | 165 | 39 | 27 | 143 | 10 | _577_ |

  <figcaption>
  Tableau 1. Sièges obtenus par groupe politique, à partir des données du ministère de l'Intérieur

  </figcaption>
</figure>
</details>

#### Un "front républicain" qui a conduit à de nombreux désistements
L'autre spécificité a été le désistement d'un nombre important de candidats entre les deux tours, notamment des groupes `NFP+` et `ENS+`, comme l'illustre la figure suivante :

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/withdrawals-dark.svg" />
  <img src="/figures/withdrawals.svg"
       alt="Nombre de candidats initialement qualifiés pour le second tour, séparés entre candidats finalement présents et désistements, pour chaque famille politique." />
  </picture>
  <figcaption>
    Les désistements se concentrent très nettement chez
    NFP+ et ENS+, ce qui transforme les voix de premier tour correspondantes en
    réservoirs de report à modéliser.
  </figcaption>
</figure>

## Créer un modèle de prédiction en partant de zéro

### Quel est l'objectif d'un modèle de prédiction ?

De manière générale, un modèle de prédiction cherche à estimer une quantité $Y$ (par exemple : température, valeur d'une action ou résultat d'une élection) à partir de données d'entrée $X$. Ici, il s'agit de prévoir le nombre de sièges obtenus par chaque groupe $Y$ à partir des résultats du premier tour $X$. 

Plutôt que de prédire un chiffre unique, on cherche souvent à prédire une _distribution de probabilité_ qui permet d'obtenir un intervalle dit "_intervalle de prédiction_"[^3], qui modélise l'incertitude du modèle.
On cherche donc à estimer $p(Y\mid X)$, la distribution des valeurs possibles de $Y$ connaissant $X$.
Un modèle peut fournir une prévision ponctuelle, par exemple la médiane, ou une région prédictive $I$ telle que
$$P(Y \in I \mid X) = 0{,}9$$. En pratique, cette région est souvent représentée sous la forme d'intervalles, par exemple : "RN+ aura entre 130 et 200 sièges"[^4].

[^3]: Parfois aussi appelé (incorrectement) "intervalle de confiance"

[^4]: Cette représentation comme un produit d'intervalles $I_{NFP+}\times\cdots\times I_{RN+}$ n'est pas strictement équivalente à une région jointe $I$, car elle traite séparément l'intervalle prédictif de chaque groupe politique.

#### Aparté : Intégrer des hypothèses dans un modèle

On le verra dans la suite du post : les modèles utilisés s'appuient sur des _paramètres_ qui permettent de régler certaines grandeurs (p. ex. le taux d'abstention au second tour). Chacun des paramètres ne constitue pas en lui-même une source d'information, mais plutôt un levier que les modèles vont exploiter pour effectuer les prédictions.

C'est la distribution de probabilité choisie pour ce paramètre qui joue ce rôle et qui incorpore nos hypothèses ou croyances dans le modèle. Plus une hypothèse est forte ou plus nous avons confiance dans une information, plus la distribution choisie va s'éloigner d'une "distribution neutre"[^5]. Dans le cadre de ce projet, on considère que l'on a peu d'information, dans la plupart des cas les distributions choisies pour les paramètres seront proches de distributions neutres. 

[^5]: Le terme "distribution neutre" n'a pas de réalité mathématique. En première approximation et pour l'intuition on peut considérer qu'il s'agit d'une distribution uniforme, rendant chaque valeur possible du paramètre équiprobable.

### Qu'est-ce qui définit un bon modèle de prévision électorale ?

La littérature académique considère qu'un bon modèle de prédiction possède deux propriétés :

- _calibration_ : les résultats observés (a posteriori) tombent dans les intervalles prédictifs à la fréquence annoncée ;
- _finesse_ (_sharpness_) : les intervalles prédictifs sont étroits.

Ainsi, un modèle peut couvrir systématiquement le résultat en prédisant entre 0 et 577 sièges pour chaque groupe, mais être très peu informatif. À l'inverse, une prévision peut être étroite et manquer souvent le résultat. Pour l'évaluation des modèles, à la fin du billet, j'utiliserai notamment une métrique qui combine proximité et dispersion : l'_energy score_.

### Les données utilisées : résultats du 1er tour et liste des désistements

Les données principales utilisées en entrée du modèle sont les [résultats du premier tour des élections législatives publiés par le ministère de l'Intérieur](https://www.data.gouv.fr/datasets/elections-legislatives-des-30-juin-et-7-juillet-2024-resultats-definitifs-du-1er-tour), ainsi que la liste des candidats au second tour, qui renseigne sur les désistements.

Concrètement, après un traitement minimal, la source d'information principale contient 4 009 lignes couvrant 577 circonscriptions. Voici l'exemple de la première circonscription de l'Ain.

| CodCirElec | Inscrits | Abstentions | Exprimes | CodNuaCand | GroupPol | NbVoix | valid_round_two |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0101 | 86 843 | 25 013 | 60 495 | `RN` | `RN+` | 23 819 | **True** |
| 0101 | 86 843 | 25 013 | 60 495 | `LR` | `LR` | 14 495 | **True** |
| 0101 | 86 843 | 25 013 | 60 495 | `UG` | `NFP+` | 14 188 | False |
| 0101 | 86 843 | 25 013 | 60 495 | `ENS` | `ENS+` | 7 063 | False |
| 0101 | 86 843 | 25 013 | 60 495 | `EXG` | `NFP+` | 419 | False |
| 0101 | 86 843 | 25 013 | 60 495 | `DSV` | `RN+` | 314 | False |
| 0101 | 86 843 | 25 013 | 60 495 | `DSV` | `RN+` | 197 | False |

Les résultats du second tour ne sont utilisés qu'à des fins d'évaluation des modèles.

### Construisons le modèle pas-à-pas : la comptabilité des voix

Pour la suite de l'analyse, je prendrai l'exemple de la première circonscription de l'Ain (0101), dans laquelle les candidats en lice au second tour sont le candidat `RN+` et le candidat `LR`, après le désistement du candidat `NFP+`. J'appelle "réservoir de voix" les voix d'un candidat éliminé ou désisté après le premier tour.

<figure>

| Groupe politique | NFP+ | DVG | ENS+ | DVD | NON_EXPRIMES | **Total** |
| --- | --- | --- | --- | --- | --- | --- |
| Réservoir de voix | 14 607| 0 | 7 063 | 0 | 26 348| 48 018|

  <figcaption>
  Tableau 2. Réservoirs de voix au second tour dans la circonscription 0101, à partir des données du ministère de l'Intérieur
  </figcaption>
</figure>

**Le but du modèle est de déterminer comment ces 48 018 voix se répartissent entre les deux candidats en lice au second tour et les suffrages non exprimés.**

#### Hypothèse 1 : abstentions, votes blancs et votes nuls forment une seule catégorie

Pour simplifier, les votes blancs, nuls et les abstentions sont regroupés dans une seule catégorie dénommée `NON_EXPRIMES`, ce qui revient à supposer que le comportement des électeurs qui s'abstiennent, votent blanc ou votent nul est identique du point de vue de leurs flux vers les candidats.

On considère par ailleurs qu'il n'y a pas de nouveaux inscrits sur les listes électorales entre les deux tours.

#### Un premier modèle très simplifié : "front anti-RN"

Prenons un modèle très simple "front anti-RN" qui enverrait toutes les voix des réservoirs de voix au parti opposé à RN+ (sauf celles des électeurs de RN+). On obtiendrait alors les résultats suivants, que l'on peut écrire sous la forme d'une matrice dite **matrice de report**  :

<figure class="flow-matrix">

| Groupe politique d'origine / cible | LR | RN+ | NON_EXPRIMES | **Total** |
| --- | --- | --- | --- | --- |
| LR | 100% (14 495) | 0 | 0 | 14 495 |
| RN+ | 0 | 100% (24 330) | 0 | 24 330 |
| NFP+ | 100% (14 607)| 0 | 0 | 14 607 |
| ENS+ | 100% (7063) | 0 | 0 | 7 063 |
| NON_EXPRIMES | 0 | 0 | 100%  (26 348) | 26 348 |
| **Total** | 36 165 (59,8 %)| 24 330 (40,2 %) | 26 348 | 86 843|

<figcaption>
Tableau 3. Illustration d'une matrice de report pour la circonscription 0101,
modèle "front anti-RN". Comme dans le schéma des flux présenté plus bas, le
bleu désigne les réservoirs qualifiés, l'orange les partis éliminés et le gris
les non-exprimés. Il faut la lire comme "100% des électeurs LR votent pour LR au 2nd tour"
</figcaption>
</figure>

<figure>

Sur la base de ces reports, que l'on peut additionner, on peut obtenir les prédictions suivantes[^6] :

| Résultats | LR | RN+ | Non exprimés |
| --- | --- | --- | --- |
| Prédits par le modèle "front anti-RN" | 36 165 | 24 330 | 26 348 |
| Réels | 33 889 | 26 116 | 26 849 |

<figcaption>
Tableau 4. Comparaison entre les résultats du modèle "front anti-RN" et les résultats réels
</figcaption>
</figure>

[^6]: La ligne « Réels » totalise 86 854 inscrits, soit 11 de plus que les 86 843 du premier tour : quelques inscriptions ont été enregistrées entre les deux tours. L'écart est négligeable ici, mais il rappelle que l'hypothèse « pas de nouveaux inscrits » n'est vraie qu'à quelques unités près.

Dans ce cas de figure précis, le modèle est **déterministe** car la matrice de report est fixée [^7], ce qui signifie qu'il renverra toujours le même résultat.

[^7]: Ici, toutes les probabilités valent 0 ou 1. Avec des probabilités intermédiaires, le tirage multinomial ajouterait une variabilité individuelle, généralement faible devant l'incertitude sur les taux de report eux-mêmes.

Un tel modèle a finalement peu d'intérêt (à part présenter le concept de matrice de report !) : il repose sur des hypothèses extrêmement fortes, généralement fausses : que 100 % des reports ont lieu vers LR.

> **À RETENIR**
>
> - L'objectif du modèle de prédiction électorale va être de prédire une matrice de probabilité de report $T$ qui détermine notamment où vont les voix des candidats éliminés.
> - Le plus gros réservoir de voix n'est pas un parti, mais les suffrages non exprimés.
> - Le modèle ne prédit pas **une** matrice de report, mais une **distribution** de matrices de report, qui donne lieu à un intervalle prédictif.

## Déterminer les matrices de probabilités de report

Il n'existe aucun moyen de connaître exactement la matrice de report $T$[^8]. Plutôt que d'en fixer arbitrairement les cellules, il est donc courant de définir une distribution $p(T)$ sur les matrices possibles. Le modèle devient _probabiliste_ et représente explicitement l'incertitude sur les reports. La nature de la distribution $p(T)$ dépend d'hypothèses sur les reports.
[^8]: On dit qu'il s'agit d'une _variable latente_

### Comment fixer la distribution de la matrice de report ?

Trois familles de flux entrent en jeu dans la matrice de report :

- les flux d'un parti éliminé vers un parti qualifié ;
- les flux d'un parti qualifié vers ce même parti ;
- les flux entrants et sortants de la catégorie des non-exprimés.

<figure>
  <img src="/figures/turnout-flows.svg"
       alt="Schéma des flux entre partis qualifiés, partis éliminés et non-exprimés entre les deux tours : fidélité, reports, démobilisation, mobilisation et rétention." />
  <figcaption>
    Les électeurs d'un candidat qualifié peuvent lui rester fidèles ou se
    démobiliser. Les électeurs d'un parti éliminé se reportent vers un candidat
    qualifié ou vers les non-exprimés ; ces derniers peuvent à leur tour se
    mobiliser ou rester non exprimés.
  </figcaption>
</figure>



Trois méthodes (non exclusives) sont possibles pour fixer la distribution des probabilités de report :

1. Effectuer un sondage auprès des électeurs pour connaître leurs intentions de vote selon le parti politique choisi au premier tour ;


2. Analyser les résultats des élections précédentes. Comme nous le verrons plus tard, les résultats agrégés ne permettent toutefois pas de reconstituer simplement ces matrices _a posteriori_[^9].

[^9]: Cette famille de problèmes est connue sous le nom d'"inférence écologique".

Ces deux premières méthodes permettent d'estimer les moyennes et les écarts-types des probabilités de report d'un parti A vers un parti B. Une fois ces quantités estimées, il est possible de faire varier chaque ligne de la matrice autour des valeurs issues du sondage en définissant une distribution de probabilité sur ces lignes. Cette méthode repose néanmoins sur les sondages ou sur des résultats d'élections précédentes, deux sources de données que je ne souhaite précisément pas utiliser.



3. La dernière méthode consiste à formuler des hypothèses simples sur les taux de report et à en déduire une distribution de la matrice. C'est cette direction que j'ai choisie.


Plutôt que de s'appuyer sur des taux historiques ou sur des taux estimés par des sondages, je vais définir un ensemble de contraintes sur des préférences.
### Flux 1 : Transfert d'un parti éliminé vers un parti qualifié

#### Hypothèse 2 : Ordres partiels de préférences de report

Je ne conserve que des préférences minimales que je juge suffisamment consensuelles. Plusieurs destinations restent donc ex æquo. Cela ne signifie pas, par exemple, que les électeurs de NFP+ préfèrent autant s'abstenir que voter RN+, simplement que je ne souhaite pas imposer leur ordre sans information plus solide.
<figure>
  <img src="/figures/preference-orderings.svg"
       alt="Ordres de préférence déclarés pour les reports de chaque groupe politique, des destinations les plus aux moins préférées." />
  <figcaption>
    Chaque ligne correspond à un groupe d'origine ; les destinations vont de la
    plus à la moins préférée. Les éléments soulignés sont ex æquo :
    le modèle refuse de les ordonner et tire leur ordre relatif à chaque
    simulation. Les contraintes restent volontairement minimales : pour les
    électeurs <code>ENS+</code>, le modèle affirme seulement que les destinations
    du premier palier sont préférées au <code>RN+</code>. Pour <code>DIV</code>, il
    ne déclare aucun ordre compte tenu de l'hétérogénéité de ce groupe.
  </figcaption>
</figure>

> Note
> 
> L'hypothèse selon laquelle il est possible de définir un ordre total de préférence entre les partis valable en toutes circonstances est discutable. En réalité, la spécificité des élections législatives de 2024 a été la mise en place de coalitions contre RN+ qui ont probablement conduit à des préférences différentes selon la présence ou non de RN+ dans la circonscription.

#### Comment traduire des préférences en probabilités de report ?

Reprenons l'exemple de la circonscription 0101 : il s'agit de traduire ces préférences en probabilités que l'on peut reporter dans la matrice $T$. Je note $t_{i,j}$ la part du réservoir d'origine du parti $i$ envoyée vers le parti $j$. Dans les formules, $\mathrm{NE}$ abrège les suffrages non exprimés.

<details>
<summary>Détail de la matrice de report</summary>

$$
T
=
\begin{array}{c|ccccccc}
\text{Origine}\backslash\text{Destination}
& \mathrm{NFP+}
& \mathrm{DVG}
& \mathrm{ENS+}
& \mathrm{LR}
& \mathrm{RN+}
& \mathrm{NON\_EXPR} \\
\hline
\color{#b56824}{\mathrm{NFP+}}      & 0 & 0 &0 & \color{#b56824}{t_{\mathrm{NFP+},\mathrm{LR}}} & \color{#b56824}{t_{\mathrm{NFP+},\mathrm{RN+}}} & \color{#b56824}{t_{\mathrm{NFP+},\mathrm{NE}}} \\
\color{#b56824}{\mathrm{ENS+}}      & 0  & 0 &0& \color{#b56824}{t_{\mathrm{ENS+},\mathrm{LR}}}  & \color{#b56824}{t_{\mathrm{ENS+},\mathrm{RN+}}} & \color{#b56824}{t_{\mathrm{ENS+},\mathrm{NE}}} \\
\color{#2a78d6}{\mathrm{LR}}        & 0 & 0 & 0&\color{#2a78d6}{\mathbf{1}} & 0 & 0 \\
\color{#2a78d6}{\mathrm{RN+}}       & 0 & 0 & 0 & 0 & \color{#2a78d6}{\mathbf{1}} & 0 \\
\color{#7b818c}{\mathrm{NON\_EXPR}} & 0  & 0 & 0 & 0 & 0 & \color{#7b818c}{\mathbf{1}}
\end{array}
$$

</details>

Pour le réservoir `ENS+` (2e ligne), les préférences supposées imposent un taux de report vers `LR` supérieur à celui vers `RN+`. Sans plus d'hypothèse, il s'agit de trouver une distribution de probabilité qui permette de tirer au hasard n'importe quelle combinaison de taux de report tels que $t_{\mathrm{ENS+},\mathrm{LR}} > t_{\mathrm{ENS+},\mathrm{RN+}}$. Une distribution dite de _Dirichlet_[^10] légèrement modifiée permet de répondre à cette contrainte.
[^10]: La distribution Dirichlet est une distribution naturelle pour modéliser un ensemble de probabilités. Elle permet de contrôler la moyenne et la dispersion des différentes probabilités échantillonnées, tout en maintenant leur somme à 1.

<details>
<summary>Détail sur la distribution de Dirichlet choisie</summary>

Une ligne de la matrice est un partage d'un même réservoir : ses composantes sont
positives et leur somme vaut 1. Le modèle tire donc un poids Gamma indépendant par
destination, puis divise chaque poids par la somme des poids. Cette construction standard
produit exactement une loi de Dirichlet symétrique : elle garantit la contrainte de
somme sans tirer puis corriger séparément chaque cellule.

La Dirichlet ne code toutefois **aucune préférence** à elle seule. Le modèle trie les
parts obtenues, attribue les plus grandes au premier palier de préférence, puis les
suivantes au deuxième. Au sein d'un même palier, l'affectation est tirée au hasard :
deux familles laissées ex æquo ne sont donc pas départagées silencieusement.

Il reste un choix, la concentration commune $\alpha$. Elle ne fixe pas la moyenne des
destinations — symétriques avant classement — mais la forme des partages : une petite
valeur favorise quelques parts très différentes, une grande valeur favorise des parts proches.


Prendre $\alpha=1$ pourrait sembler être le choix par défaut ; c'est pourtant déjà
une hypothèse, car cette valeur échantillonne uniformément l'ensemble des partages
possibles avant application de l'ordre.

L'ordre ordinal n'impose toutefois aucun écart minimal : affirmer que `ENS+` préfère `LR` à `RN+` ne dit pas si leurs taux de report diffèrent de 2 ou de 20 points. Je fais donc une hypothèse supplémentaire, volontairement faible mais réelle : les partages très proches sont un peu moins plausibles que les partages plus tranchés.

Dès lors, plutôt que d'imposer $\alpha=1$, j'autorise $\alpha$ à varier dans l'intervalle $\left[0{,}5, 1\right]$. Comme il s'agit d'un paramètre d'échelle, j'accorde le même poids aux rapports
multiplicatifs en utilisant une loi log-uniforme :

Pour chaque simulation, un unique $\alpha$ national est donc échantillonné selon la loi

$$\log\alpha \sim \mathcal U(\log(0{,}5),\log 1).$$
Effet théorique de $\alpha$

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/dirichlet-simplex-dark.svg" />
    <img src="/figures/dirichlet-simplex.svg"
         alt="Densités théoriques des taux de report ENS+ vers LR et RN+ dans un partage ordonné à deux destinations, pour alpha égal à 0,5, 0,75 et 1." />
  </picture>
  <figcaption>
    Pour isoler le rôle de $\alpha$, cette figure simplifie provisoirement la
    ligne <code>ENS+</code> à deux destinations complémentaires. Deux variables
    Gamma sont normalisées ; la plus grande part est attribuée à <code>LR</code>
    et la plus petite à <code>RN+</code>. Les deux densités théoriques sont donc
    symétriques autour de 50 %, et la contrainte
    $t_{\mathrm{ENS+},\mathrm{LR}}>t_{\mathrm{ENS+},\mathrm{RN+}}$ est toujours
    respectée. Plus $\alpha$ diminue, plus les reports proches de 0 % ou de 100 %
    deviennent probables. Dans le modèle complet, les non-exprimés constituent
    une troisième destination : les deux distributions marginales ne sont alors
    plus exactement symétriques.
  </figcaption>
</figure>
</details>

En pratique, même si aucune valeur explicite de taux de report n'est fixée (et c'est l'intérêt de ce modèle), le choix de cet ordre et de cette distribution induit mécaniquement une distribution sur les taux de reports qu'il est possible de visualiser. Ainsi la figure suivante décrit pour deux configurations différentes, les taux de reports déduits de l'ordre de préférence partiel.
<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/prior-transfer-composition-dark.svg" />
    <img src="/figures/prior-transfer-composition.svg"
         alt="Distribution prédictive a priori des reports de voix dans les duels ENS+/RN+ et NFP+/RN+, selon le réservoir politique d'origine." />
  </picture>
  <figcaption>
    Illustration de la distribution prédictive a priori pour deux types de duels (ENS+/RN+ et NFP+/RN+). On peut y voir les taux de reports "déduits" par le modèle du fait de l'ordre partiel de préférences imposé.
  </figcaption>
</figure>

### Flux 2 : Parti qualifié vers ce même parti et démobilisation

#### Hypothèse 3 : les électeurs d'un candidat qualifié peuvent se démobiliser, mais pas voter pour un autre candidat

Il n'y a pas de raison, a priori, que tous les électeurs ayant voté au premier tour pour un candidat qualifié revotent pour lui au second. Je suppose donc qu'un tel électeur peut se démobiliser (ne pas exprimer de suffrage), avec une probabilité faible, mais pas voter pour l'autre candidat.

Un taux national de démobilisation $d$ est tiré une fois par simulation et partagé par tous les candidats qualifiés. Ce taux réel étant inconnu, on considère qu'il suit une distribution de probabilité avec un intervalle prédictif relativement large tout en considérant qu'il est peu probable que plus de 10% des électeurs pour un parti qualifié se démobilisent. 

<details>
<summary>Hyperparamètres du taux de démobilisation</summary>

Le prior est une distribution bêta dont la moyenne est très basse (5 %) et l'intervalle central à 90 % vaut $\left[0{,}9\,\%, 11{,}7\,\%\right]$.

$$
d\sim\operatorname{Beta}(2,38).
$$

Pour isoler l'effet du niveau de démobilisation de celui de la dispersion de son
prior, je fixe ensuite $d$ à cinq valeurs comprises entre 0 % et 20 %. Les autres
paramètres continuent d'être tirés normalement.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/demobilisation-sensitivity-dark.svg" />
    <img src="/figures/demobilisation-sensitivity.svg"
         alt="Intervalles prédictifs de sièges par famille politique lorsque le taux national de démobilisation est fixé successivement à 0, 5, 10, 15 et 20 %." />
  </picture>
  <figcaption>
    Médiane et intervalle prédictif central à 90 % avec le modèle national ancré,
    pour 2 000 simulations par valeur de $d$. Aucun résultat du second tour
    n'intervient. Les échelles horizontales diffèrent entre panneaux afin de
    rendre visibles les déplacements des petits groupes. La valeur $d=0$ sert de
    référence expérimentale ; elle ne correspond pas au prior retenu.
  </figcaption>
</figure>

Les intervalles se recouvrent très largement, même sur cette grille volontairement
étendue. Entre $d=0$ et $d=20\,\%$, la médiane passe de 173 à 163 sièges pour
`RN+`, de 145,5 à 150,5 pour `ENS+` et de 203 à 205 pour `NFP+`. Une forte
démobilisation réduit donc bien l'avantage acquis au premier tour par `RN+`, mais
son effet sur le centre de la prédiction reste faible au regard de l'incertitude
totale. L'intervalle de `RN+` s'élargit davantage : sa largeur passe de 132 à 150
sièges. Dans la zone couverte par le prior retenu — essentiellement entre 1 % et
12 % — les différences sont encore plus limitées.
</details>

En fin de compte, le flux net de votants pour un parti qualifié, par exemple le `RN+` est la somme des électeurs du RN+ qui ne se sont pas démobilisés, d'électeurs issus de partis éliminés qui se reportent vers le RN+ (voir partie précédente), et de personnes s'étant abstenues au premier tour qui se mobilisent pour le RN (voir partie suivante).

Ainsi, dans le cas de la circonscription 0101, en considérant par exemple $d=0{,}1$, le nombre d'électeurs de RN+ au second tour est donné par la formule :
$$
V_{RN+, 0101} = \underbrace{90\,\%}_{\text{10\,\% de démobilisation}}\times\underbrace{24330}_{\text{électeurs RN+ au premier tour}} + \text{reports d'autres partis} + \text{nouveaux votants}
$$

Plus le taux de démobilisation augmente, moins l'avance acquise au premier tour pèse par rapport aux reports de voix.

### Flux 3 : Depuis et vers les suffrages non exprimés

Modéliser les suffrages non exprimés est crucial, car ils constituent le plus grand réservoir de voix. Les projections peuvent donc être particulièrement sensibles à la manière dont leur évolution est représentée.

Or, la part de suffrages exprimés est difficile à modéliser, car elle résulte notamment de la combinaison de trois phénomènes :

- la configuration de la circonscription : duel, triangulaire ou quadrangulaire ;
- l'identité des candidats qualifiés ;
- des facteurs externes, par exemple la météo.

Si la majorité des personnes n'ayant pas exprimé de suffrage au premier tour restent dans cette catégorie, certaines votent au second. Inversement, des électeurs de partis qualifiés ou éliminés peuvent cesser d'exprimer un suffrage.


#### Hypothèse 4 : le nombre de "nouveaux votants" est proportionnel au réservoir des non-exprimés

Implicitement, le modèle suppose qu'une proportion fixée par la matrice de report des personnes n'ayant pas exprimé de suffrage au premier tour en exprimera un au second.

Cela signifie que plus le réservoir des non-exprimés est grand au premier tour, plus le nombre absolu de personnes susceptibles de se mobiliser au second est important.

Cette hypothèse simplifie le modèle, mais reste difficile à défendre. Une variante plus souple sera introduite par la suite.

Il reste à répartir les non-exprimés qui se mobilisent entre les candidats
qualifiés.

#### Répartition des nouveaux votants entre partis
Je n'ai volontairement fait que très peu d'hypothèses sur la répartition des nouveaux électeurs (s'étant abstenus au premier tour, par exemple). Il est difficile de savoir si ces électeurs :
- se répartissent de manière égale entre les deux candidats du second tour ;
- se répartissent proportionnellement aux scores du premier tour ;
- à l'inverse, cherchent à soutenir le candidat le moins favorisé du premier tour.

#### Hypothèse 5 : pas de répartition privilégiée pour la remobilisation
Pour modéliser ces différentes situations, j'ai introduit un paramètre à l'échelle nationale dit de _tilt_ qui gère la répartition du réservoir de nouveaux votants. Selon sa valeur, il les répartit plutôt vers le candidat dominant, vers le candidat perdant ou équitablement, et ce de manière équiprobable.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/tilt-effect-dark.svg" />
    <img src="/figures/tilt-effect.svg"
         alt="Répartition des non-exprimés qui se mobilisent entre deux candidats selon deux rapports de force du premier tour et trois valeurs du tilt." />
  </picture>
  <figcaption>
    La part attribuée au candidat $k$ est proportionnelle à $s_k^{\tau}$, où $s_k$
    est son score parmi les deux finalistes au premier tour. Pour $\tau=-1$, le
    candidat arrivé derrière est favorisé ; pour $\tau=0$, le flux est partagé à
    parts égales ; pour $\tau=1$, il reproduit exactement le rapport de force du
    premier tour. Le
    prior actuel tire $\tau$ uniformément entre $-1$ et $1$ une fois par simulation.
  </figcaption>
</figure>


#### Mettons tout bout à bout !

Pour suivre un même scénario jusqu'au résultat, prenons un tirage où
$\alpha=0{,}70$, le taux de démobilisation vaut 4 %, la rétention des
non-exprimés 90 % et le tilt 0.

La figure suivante illustre le tirage choisi des paramètres par rapport à leur distribution de probabilité. On y constate par ailleurs, que les paramètres $\alpha$ et $\tau$ contiennent peu d'information (proches d'une distribution neutre). À l'inverse $t_{NE,NE}$, le taux de rétention des suffrages et surtout $d$ le taux de démobilisation contiennent beaucoup plus d'information. Cette information n'est pas étayée par des sondages ou des analyses historiques mais davantage par du bon sens et parfois de l'intuition.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/simulation-parameter-draws-dark.svg" />
    <img src="/figures/simulation-parameter-draws.svg"
         alt="Densités a priori de la concentration, de la démobilisation, de la rétention des non-exprimés et du tilt, avec la valeur utilisée dans l'exemple indiquée sur chacune." />
  </picture>
  <figcaption>
    Les quatre variables sont tirées une fois au niveau national. Les hauteurs
    des courbes ne sont pas comparables d'un panneau à l'autre : chaque prior a
    sa propre échelle.
  </figcaption>
</figure>

##### 1. Tirage du flux 1 (partis éliminés -> partis qualifiés + abstention )
En considérant les trois familles de flux décrites précédemment pour la circonscription 0101, après le retrait du candidat `NFP+`, le second tour oppose `LR` à
`RN+`. Les 14 607 voix `NFP+` et les 7 063 voix `ENS+` constituent deux réservoirs éliminés. La ligne utile du premier est

$$
T_{\mathrm{NFP+}}=(t_{\mathrm{NFP+},\mathrm{LR}},\ t_{\mathrm{NFP+},\mathrm{RN+}},\
t_{\mathrm{NFP+},\mathrm{NE}}).
$$

L'ordre déclaré devient simplement

$$LR \succ \{RN+,\mathrm{NON\_EXPRIMES}\}.$$

Le modèle commence par tirer au hasard un ordre total de préférence, par exemple $LR \succ RN+ \succ \text{NON\_EXPRIMES}$, puis il tire 
des taux de report compatibles avec cet ordre total, selon une distribution de Dirichlet améliorée.
Il peut par exemple attribuer 62 % des voix `NFP+` à `LR`, 25 % à `RN+`
et 13 % aux non-exprimés. Il procède de la même manière pour les voix `ENS+`.
Ainsi, on obtient :
<figure>

| Groupe politique d'origine / cible | LR | RN+ | NON_EXPRIMES | **Total** |
| --- | --- | --- | --- | --- |
| NFP+ | 62% | 25% | 13% | 100%|
| ENS+ | 71%  | 19% | 10% | 100% |
<figcaption>
Flux 1 pour la circonscription 0101
</figcaption>
</figure>

##### 2. Tirage du flux 2 (partis qualifiés -> partis qualifiés + abstention)

Ensuite, le modèle tire un taux de démobilisation par exemple de 4%, on obtient donc : 
<figure>

| Groupe politique d'origine / cible | LR | RN+ | NON_EXPRIMES | **Total** |
| --- | --- | --- | --- | --- |
| LR | 96%| 0% | 4% | 100% |
| RN+ | 0% | 96% | 4% | 100% |
<figcaption>
Flux 2 pour la circonscription 0101
</figcaption>
</figure>

##### 3. Tirage du flux 3 (`NON_EXPRIMES` -> tous partis)
Puis on tire un taux de rétention de 90% des suffrages non-exprimés et un tilt de 0. Cela signifie que les 10% des abstentionnistes du 1er tour qui se remobilisent sont répartis équitablement entre candidats :
<figure>

| Groupe politique d'origine / cible | LR | RN+ | NON_EXPRIMES | **Total** |
| --- | --- | --- | --- | --- |
| NON_EXPRIMES | 5% | 5% | 90% | 100%  |
<figcaption>
Flux 3 pour la circonscription 0101
</figcaption>
</figure>

##### Matrice de report complète échantillonnée
<figure class="flow-matrix">

| Groupe politique d'origine / cible | LR | RN+ | NON_EXPRIMES | **Total** |
| --- | --- | --- | --- | --- |
| LR | 96%| 0% | 4% | 100% |
| RN+ | 0% | 96% | 4% | 100% |
| NFP+ | 62% | 25% | 13% | 100%|
| ENS+ | 71%  | 19% | 10% | 100% |
| NON_EXPRIMES | 5% | 5% | 90% | 100%  |
</figure>

##### Cas particulier de la circonscription 0101
En prenant en compte les divers réservoirs de voix, on obtient les reports suivants : 

Les 24 330 voix `RN+` regroupent ici les 23 819 voix du candidat qualifié et
les 511 voix (314 + 197) de deux autres candidats de la même famille politique,
conformément à l'agrégation utilisée par le modèle.

<figure class="flow-matrix">

| Groupe politique d'origine / cible | LR | RN+ | NON_EXPRIMES | **Total** |
| --- | --- | --- | --- | --- |
| LR | 13 915 | 0 | 580 | 14 495 |
| RN+ | 0 | 23 357 | 973 | 24 330 |
| NFP+ | 9 056 | 3 652 | 1 899 | 14 607|
| ENS+ | 5 015  | 1342 | 706 | 7 063 |
| NON_EXPRIMES | 1 317 | 1 317 | 23 714 | 26 348 |
| Total | **29 303** | **29 668** | **27 872** | **86 843**|
</figure>

On peut représenter le même tirage sous la forme d'un diagramme de flux :
<figure>
  <img src="/figures/prior-sankey.svg"
       alt="Diagramme des flux de voix du tirage illustratif dans la circonscription 0101, du premier vers le second tour." />
  <figcaption>
    La largeur des rubans représente un nombre de voix, et non un taux de report.
    La figure reprend les réservoirs du premier tour et les taux tirés dans les
    trois étapes précédentes ; elle ne représente qu'une simulation possible.
  </figcaption>
</figure>


### Passer à l'échelle nationale
Jusqu'à présent, j'ai pris l'exemple d'une circonscription. Comment étendre le modèle aux 501 circonscriptions à prédire ?

#### Hypothèse 6 : absence de variations locales

Pour ce premier modèle, je suppose que les préférences de report sont uniformes dans toute la France. Ce qui signifie que la probabilité qu'un électeur NFP+ se reporte sur ENS+ est la même dans l'Ain ou à Paris, par exemple. En conséquence, une seule matrice $T$ est utilisée pour toute la France.

Ainsi il n'y a qu'une seule matrice de report à prédire, réutilisée par toutes les circonscriptions.
Cette hypothèse est assez peu réaliste, je montrerai par la suite comment adapter le modèle aux variations locales.

> **À RETENIR**
>
> - Le modèle ne déclare jamais des taux de report, mais des ordres partiels de préférences entre reports.
> - De fait, ces ordres induisent mécaniquement des contraintes sur les valeurs possibles de taux de report, tout en laissant une incertitude.
> - À titre d'exemple sur un duel NFP+/RN+, le modèle estime que le taux de report d'ENS+ vers NFP+ est compris entre 46 % et 98 % (à 90 %).

<details>
<summary>Résumé mathématique du modèle</summary>

Le modèle cherche à estimer $Y$, le nombre de sièges par parti, à partir de $X$, les
résultats du premier tour. 
Il s'appuie sur deux variables _latentes_ nationales : la matrice de report $T$ et le
taux de démobilisation $d$, ainsi que sur un paramètre $\alpha$, lui aussi inconnu, qui règle la conversion des préférences en probabilités ; on note $\Theta=(T,d,\alpha)$ l'ensemble des trois.

Le modèle étant probabiliste, ce qu'il estime est une distribution :

$$
p(Y \mid X) = \int p(Y \mid \Theta, X)\, p(\Theta \mid X)\, d\Theta
$$

Pour ce premier modèle, la distribution de la matrice de report n'utilise pas les
résultats du premier tour : $p(\Theta \mid X) = p(\Theta)$, et

$$
p(Y \mid X) = \int p(Y \mid \Theta, X)\, p(\Theta)\, d\Theta
$$

Le premier facteur, $p(\Theta)$, est la distribution décrite dans les paragraphes
précédents :
$$
p(\Theta) = p(T,d,\alpha) = p(\alpha)p(d)p(T|d,\alpha)

$$

Le second, $p(Y \mid X,\Theta)$, est le passage des taux de report au nombre
de sièges — presque une simple opération arithmétique :
$$
p(Y|X) = \int p(\alpha)p(d)p(T|d,\alpha)p(Y|T,X) d\alpha dd dT
$$

En notant $T_c=(t_{c,i,j})_{i,j}$ la matrice adaptée à la circonscription $c$
et $n_{c,i}$ la taille du réservoir du parti $i$, le vecteur des reports de ce réservoir
vers toutes les destinations suit une loi multinomiale :

$$
R_{c,i}\sim\mathcal{M}\left(n_{c,i},\ t_{c,i,\cdot}\right)
$$

Le vecteur des voix de la circonscription est la somme de ces reports :

$$
V_c = \sum_{i} R_{c, i}
$$

Et le nombre de sièges du parti $i$ compte les circonscriptions qu'il remporte :

$$
Y_i = \sum_{c} \mathbf{1}\left[\arg\max V_c = i\right]
$$

La quasi-intégralité de l'incertitude vient du premier facteur ; le second est presque
déterministe.
</details>

Et sur plusieurs tirages, la distribution prédictive apparaît progressivement :

<figure>
  <picture>
    <source media="(prefers-reduced-motion: reduce) and (prefers-color-scheme: dark)" srcset="/figures/district-0101-simulations-dark.png" />
    <source media="(prefers-reduced-motion: reduce)" srcset="/figures/district-0101-simulations.png" />
    <source media="(prefers-color-scheme: dark)" srcset="/figures/district-0101-simulations-dark.gif" />
    <img src="/figures/district-0101-simulations.gif"
         alt="Animation de 20 000 simulations de la circonscription 0101 : chaque point représente les parts de LR et RN+ parmi les inscrits, tandis que la fréquence cumulée de victoire de LR se stabilise." />
  </picture>
  <figcaption>
    Chaque point est un second tour simulé dans la circonscription 0101. Les deux
    axes donnent les parts de LR et RN+ parmi les inscrits ; les diagonales
    indiquent la part complémentaire de non-exprimés. La fréquence affichée est
    recalculée après chaque groupe de tirages.
  </figcaption>
</figure>

<details>
<summary>Détails formels de la simulation</summary>

La simulation découle naturellement de la décomposition de $p(Y\mid X)$ décrite dans la partie précédente :

- on échantillonne les taux de report $T\sim p(T)$ ;
- on tire le taux national de démobilisation $d\sim\operatorname{Beta}(2,38)$ ;
- pour chaque circonscription, on adapte $T$ aux candidats qualifiés et à leur démobilisation afin d'obtenir $T_c$ ;
- on effectue un tirage multinomial pour ventiler le réservoir de voix de chaque groupe ;
- on en déduit le résultat de la circonscription, $V_c$ ;
- on agrège les sièges à l'échelle nationale pour obtenir $Y$.

On répète cette simulation $N$ fois et l'on obtient une estimation de $p(Y\mid X)$ par la méthode de Monte-Carlo.

Cela permet d'obtenir directement des intervalles de prédiction à 90 % et d'effectuer des analyses conditionnelles, par exemple : "Lorsque la part de non-exprimés simulée varie, comment la projection de sièges évolue-t-elle dans le modèle ?"

</details>

### Les faiblesses de ce modèle

Ce modèle repose sur deux hypothèses simplificatrices : 
- les comportements sont les mêmes partout en France (hypothèse 6) ;
- le taux de suffrage exprimés est mal contrôlé (hypothèse 4)

La partie suivante décrit comment construire un modèle sans ces deux hypothèses.

## Vers un modèle plus complexe ?

Le modèle construit jusqu'ici, identifié par la suite comme le modèle `national`, ignore les variations locales et ne modélise les suffrages exprimés qu'indirectement.

### Amélioration #1 : Une meilleure modélisation des suffrages non-exprimés ?

La modélisation de la rétention des suffrages non exprimés via le paramètre de la matrice de report $t_{\mathrm{NE},\mathrm{NE}}$ (l'hypothèse 4) introduit un biais de remobilisation au second tour.

**Exemple** : 
Circonscription 5908 : Dans cette circonscription du Nord, le taux de suffrages exprimés était très bas au premier tour (52,1%). En tirant des valeurs standards des différents paramètres on constate que le mécanisme actuel conduit mécaniquement à une diminution de l'abstention au 2nd tour, qui n'a aucune raison en réalité de se produire.

<figure>
  <img src="/figures/non-expressed-balance.svg"
       alt="Schéma des flux entre partis qualifiés, partis éliminés et non-exprimés entre les deux tours : fidélité, reports, démobilisation, mobilisation et rétention." />
  <figcaption>
    Schéma des flux entre partis qualifiés, partis éliminés et non-exprimés entre les deux tours. Illustration du mode de calcul du modèle national
  </figcaption>
</figure>

En réalité, le réservoir de voix non-exprimées étant supérieur à celui de n'importe quel parti, il me semblait primordial d'avoir une bonne modélisation du taux de suffrages exprimés dans chaque circonscription, davantage même qu'avoir une bonne modélisation des reports entre partis.

Plutôt que de contrôler un seul taux de report, qui est une variable pour laquelle nous n'avons pas beaucoup d'information, j'ai souhaité contrôler la part de suffrages exprimés au 2nd tour par circonscription. Cette cible impose une contrainte commune à tous les flux vers les non-exprimés[^11].
[^11]: Comme nous le verrons juste après, une même cible peut être atteinte par plusieurs combinaisons de flux.

Pour fixer la part de suffrages exprimés au 2nd tour, je considère qu'il s'agit de la somme entre la part de suffrages exprimés du premier tour (considérée comme une "ancre"), une dérive nationale entre les deux tours et une variation aléatoire locale[^12].
[^12]: En réalité la somme a lieu en échelle "logit" qui permet d'avoir un pourcentage entre 0 et 100 % sans effectuer une soustraction identique pour toutes les circonscriptions.

Classiquement la dérive nationale entre les deux tours est négative : le taux de participation au 2nd tour est souvent inférieur au premier tour. En l'absence d'informations plus précises cette dérive est fixée à 0 en moyenne et est autorisée à varier de manière assez significative.

<details>
<summary> Équation du taux de suffrage exprimés </summary>
Notons :

- $r_{c,1}$ (resp. $r_{c,2}$) le taux de suffrages exprimés au premier tour (resp. second tour) pour la circonscription $c$
- $\delta_{nat}$ la dérive nationale : si elle est positive, il y a davantage de suffrages exprimés à l'échelle nationale au 2nd tour qu'au premier
- $\delta_c$ une variation locale (au niveau de la circonscription $c$)


$$
\text{logit}(r_{c,2}) = \text{logit}(r_{c,1})+\delta_{nat}+\delta_c
$$

Comme le montre le schéma ci-dessous, le paramètre contrôlé n'est plus un taux sur un flux mais la valeur du solde net de tous les flux conduisant à une augmentation ou diminution du pourcentage de suffrages exprimés.
</details>
<figure>
  <img src="/figures/non-expressed-anchored.svg"
       alt="Schéma des flux entre partis qualifiés, partis éliminés et non-exprimés entre les deux tours : fidélité, reports, démobilisation, mobilisation et rétention." />
  <figcaption>
    Schéma des flux entre partis qualifiés, partis éliminés et non-exprimés entre les deux tours avec le nouveau mode de calcul du taux de suffrages non-exprimés.
  </figcaption>
</figure>

#### Identifiabilité des suffrages exprimés

Il n'est pas possible de déduire simplement à partir du taux de suffrages exprimés le taux de rétention (électeurs non exprimés aux 2 tours). En effet, les suffrages exprimés suivent plusieurs chemins comme expliqué précédemment.

<details>
<summary>Comment en déduire les paramètres de la matrice de report ?</summary>

La cible fixée sur le taux de suffrages non-exprimés contraint le solde net de tous les flux vers les non-exprimés, mais pas leur provenance. La rétention des non-exprimés, la démobilisation des électeurs qualifiés et les reports des partis éliminés vers les non-exprimés ont pourtant déjà chacun une distribution a priori.

Le modèle part donc d'un tirage de tous ces taux, puis cherche la combinaison compatible avec la cible (taux de suffrages non-exprimés) qui s'en écarte le moins en minimisant la somme des divergences de Kullback-Leibler entre les probabilités avant et après ajustement, pondérées par la taille de chaque réservoir de voix. La solution revient à appliquer simultanément le même décalage sur l'échelle logit à tous les flux vers les non-exprimés.

Les reports entre candidats parmi les suffrages exprimés ne changent pas : seule la part allant vers les non-exprimés varie, et toutes les autres parts de la ligne sont redimensionnées dans la même proportion. Les contraintes issues des ordres de préférence restent également respectées. Si une cible se trouve hors de l'ensemble physiquement réalisable, elle est ramenée à sa frontière.

Cette opération constitue une approximation calculable de la projection de toute la loi jointe du modèle : cette dernière demanderait de connaître la densité de participation induite conjointement dans les 501 circonscriptions.
</details>

Visualisons maintenant les taux de suffrages exprimés produits par la distribution prédictive *a priori* (sans utiliser les résultats du second tour).
<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/expressed-share-dark.svg" />
    <img src="/figures/expressed-share.svg"
         alt="Histogramme de la distribution prédictive de la part nationale de suffrages exprimés sous le modèle national ancré." />
  </picture>
  <figcaption>
    Distribution prédictive a priori de la part nationale de suffrages exprimés.
    La bande indique l'intervalle central à 90 % et le trait sa médiane. Le
    résultat du second tour n'intervient pas dans cette distribution.
  </figcaption>
</figure>

### Amélioration #2 : Modélisation de comportements locaux
Il n'y a aucune raison, a priori, que le comportement des électeurs soit le même partout en France. Pour pallier ce défaut, une première idée serait de tirer une matrice de report $T_c$ par circonscription, de manière indépendante.

#### Un subtil mélange de tendance nationale et de spécificités locales

#### Hypothèse 6B : Comportement d'un électeur = tendance nationale + spécificité locale

En réalité, il est raisonnable de supposer que les comportements des électeurs dans une circonscription sont le résultat d'une tendance nationale et de spécificités locales qui peuvent changer leur comportement à la marge par rapport à cette tendance. 

Cela conduit naturellement à introduire une structure hiérarchique où une matrice nationale est partagée par toutes les circonscriptions et une matrice locale spécifique à chaque circonscription, la matrice de report totale étant un mélange de ces deux matrices, modulé par un coefficient $\lambda$, ce qui peut s'écrire pour une circonscription $c$[^13] : 

$$
T_{c} = \lambda \times T_{nat} + (1-\lambda) \times T_{local, c}
$$
[^13]: Il ne s'agit pas exactement de la manière dont le modèle a été réellement implémenté
<details>
<summary> Comment choisir le coefficient de mélange $\lambda$ ? </summary>

Le modèle précédent (`national`) correspond à $\lambda=1$. À l'inverse, un modèle complètement local correspondrait à $\lambda = 0$. En pratique, comme on ne connaît pas sa valeur réelle, $\lambda$ est tiré selon une distribution Beta de paramètre (4,2). Cette distribution matérialise notre hypothèse selon laquelle le comportement local est une variation "à la marge", donc que les valeurs de $\lambda$ sont davantage concentrées vers la droite entre 0,5 et 1 tout en laissant de nombreuses valeurs possibles.
</details>

#### Comment fixer les variations locales des matrices de report ?

Si l'on sait que des variations locales existent, on ne connait pas pour autant leur direction : on ignore, par exemple, si les électeurs se reportent davantage vers RN+ dans telle circonscription plutôt que telle autre. On peut en revanche exprimer une structure de dépendance : _« Je ne sais pas dans quel sens cette circonscription s'écartera de la moyenne, mais une circonscription politiquement similaire aura probablement un écart du même sens. »_

Le choix retenu est donc de conserver dans toutes les circonscriptions la même distribution pour la matrice de report, mais lui donner une structure de corrélation spécifique : les matrices locales ne sont plus indépendantes[^14]. L'introduction d'une corrélation change uniquement leur dépendance : selon la part de variation nationale et la portée des corrélations locales, les incertitudes peuvent alors davantage se compenser ou, au contraire, s'additionner dans les projections nationales.

[^14]: La _distribution marginale_ des matrices $T_c$ reste la même que dans le modèle précédent. En d'autres termes, prise séparément, chaque matrice de report locale a la même loi, donc les mêmes statistiques, que la matrice nationale. En revanche, prises à l'échelle nationale, certaines matrices bougent « ensemble », ce qui peut conduire à une modification des résultats.

De la même manière, on peut considérer que le tilt, qui indique la manière dont les électeurs se mobilisant au 2nd tour après s'être abstenus au 1er tour se répartissent entre les partis qualifiés, suit le même modèle hiérarchique national/local avec corrélation.

#### Choisir la structure de dépendance : comment les circonscriptions sont-elles corrélées entre elles ?

Si l'on peut raisonnablement supposer que les taux de report sont corrélés entre circonscriptions, il est plus complexe de déterminer la source de cette corrélation. Il peut s'agir :
- de variations sociodémographiques dans le profil des électeurs ;
- de nuances politiques entre candidats, par exemple un candidat `NFP+` issu de LFI et un candidat `NFP+` issu du PS peuvent susciter des comportements différents ;
- d'autres facteurs locaux.

#### Hypothèse 6C : Les taux de reports sont corrélés entre circonscriptions d'une même région et d'un même département

Contrairement à l'hypothèse qui supposait l'absence de variations locales, on autorise dans ce modèle des variations locales, corrélées selon le département de la circonscription. Plus précisément deux circonscriptions d'un même département sont davantage corrélées que deux d'une même région mais de départements différents, elles-mêmes davantage corrélées que deux circonscriptions de deux régions différentes. 

<details>
<summary>L'écriture formelle du mélange national/local</summary>

Une moyenne directe de deux matrices modifierait la distribution marginale des taux de
report. Le mélange est donc effectué sur une échelle gaussienne latente, avant la
transformation en probabilités :

$$
z_c = \sqrt{\lambda}\,z^{nat}
      + \sqrt{1-\lambda}\,z^{loc}_c,
$$

où $z^{nat}\sim\mathcal N(0,1)$ est partagé par toutes les circonscriptions et
$z^{loc}\sim\mathcal N(0,K)$ correspond à une composante locale.

En pratique on fixe $K$ de la manière suivante : 
- $K_{c,c} = 1$
- $K_{c_{1}, c_2} = \rho_{d}$ si $c_1$ et $c_2$ sont dans le même département
- $K_{c_1, c_2} = \rho_{r}$ si $c_1$ et $c_2$ sont dans la même région mais dans des départements différents
- $K_{c_1, c_2} =0$ sinon

Comme $K_{cc}=1$, chaque $z_c$ reste marginalement distribué selon $\mathcal N(0,1)$. Entre deux circonscriptions $c_1$ et $c_2$,
la covariance latente vaut :

$$
\operatorname{Cov}(z_{c_1},z_{c_2})
=
\lambda+(1-\lambda)K_{c_1, c_2}.
$$

Ainsi, en prenant par exemple $\rho_d=0,7$ et $\rho_r=0,3$ et $\lambda=0,6$, les corrélations sont : 
- Au sein d'un même département : 0,88
- Au sein d'une même région : 0,72
- Entre deux régions différentes : 0,6 ($\lambda$)

Concernant le tirage de $z^{loc}_c$ : 
- Pour chaque région $r$ on tire $z^R_{r}\sim\mathcal{N}(0,1)$
- Pour chaque département $d$ on tire $z^D_{d}\sim\mathcal{N}(0,1)$
- Pour chaque circonscription on tire $\varepsilon_c$

On peut montrer qu'en fixant : 
$$
z^{loc}_c = \sqrt{\rho_r}z^R_{r(c)} + \sqrt{\rho_d-\rho_r}z^D_{d(c)}+\sqrt{1-\rho_d}\varepsilon_c
$$
on a bien une variable aléatoire aux propriétés recherchées.
</details>
L'illustration suivante fournit un exemple sur une circonscription des corrélations entre taux de report pour une ligne de la matrice.
<figure>
  <img src="/figures/national-local-mixing.svg"
       alt="Impact du coefficient de mélange sur une ligne de report" />
  <figcaption>
Impact du coefficient de mélange lambda sur les taux de reports selon que les circonscriptions soient au sein d'un même département (donc corrélées) ou non
  </figcaption>
</figure>

### Mettons tout ensemble !
Les variables tirées dans une simulation du modèle local ancré peuvent maintenant
être rassemblées en une seule vue :

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/anchored-parameter-draws-dark.svg" />
    <img src="/figures/anchored-parameter-draws.svg"
         alt="Densités a priori des paramètres du modèle local ancré, organisées en trois lignes : paramètres partagés avec le modèle national, paramètres d'ancrage de l'abstention et paramètres locaux." />
  </picture>
  <figcaption>
    Dans le modèle ancré, la rétention des non-exprimés est d'abord tirée puis
    ajustée conjointement avec les autres flux vers les non-exprimés. Les deux
    deltas sont exprimés sur l'échelle logit. Les distributions de $\rho_d$ et $\rho_r$
    sont celles déclarées avant l'application de la contrainte
    $\rho_r\leq\rho_d$.
  </figcaption>
</figure>

### Résumé du modèle `local ancré`

| Hypothèse | Statut |
| --- | --- |
|1 : Assimilation des votes blancs et nuls au comportement des abstentionnistes| Conservée|
|2 : Ordres de préférences partiels | Conservée|
|3 : Démobilisation d'électeurs d'un parti qualifié| Conservée|
|4 : Nombre de nouveaux votants proportionnel au réservoir de non exprimés | Supprimée (ancre) |
|5 : Pas de répartition privilégiée pour la remobilisation| Conservée |
|6 : Absence de variations locales | Supprimée |
|6B : Comportement d'un électeur = tendance nationale + spécificité locale | Ajoutée (mélange national/local via $\lambda$) |
|6C : Corrélation départementale et régionale des taux de reports| Ajoutée (noyau) |

<details>
<summary>Les détails des paramètres du modèle</summary>

Comme précédemment :

$$
p(Y \mid X) = \int p(Y \mid X, \Theta)\, p(\Theta \mid X)\, d\Theta
$$

mais $\Theta$ n'est plus indépendant de $X$ : les résultats du premier tour servent à calculer
le noyau **et** l'ancre de participation. La distribution conditionnelle se factorise dans
l'ordre où le simulateur tire effectivement :

$$
p(\Theta \mid X) =
\underbrace{p(\lambda)p(\rho_d|X)p(\rho_r|X)p(\alpha)p(\delta_{nat})}_{\text{hyperparamètres aléatoires}}
\;\cdot\;
\underbrace{p\!\left(r_{\cdot,2} \mid X, \delta_{nat}\right)}_{\text{ancre de participation}}
\;\cdot\;
\underbrace{p(d)p\!\left(T_c \mid K(\rho_d, \rho_r), \alpha, r_{\cdot,2}\right)}_{\text{taux de report}}
$$
Loi des paramètres :

_Communs au modèle `national`_
- Coefficient de concentration $\alpha$ : $\log(\alpha)\sim\text{LogU}(\log(0{,}5), \log(1))$
- Coefficient de démobilisation $d\sim\operatorname{Beta}(2, 38)$

_Spécifiques au modèle `national_ancré` et `local_ancré`_

- $r_{\cdot, 2} | X, \delta_{nat} : \text{logit}(r_{\cdot, 2}) = \text{logit}(r_{\cdot, 1}) + \delta_{nat} + \delta_c$


_Spécifiques au modèle `local_ancré`_.
- Coefficient de mélange $\lambda\sim\operatorname{Beta}(4,2)$
- $\rho_d$ : la corrélation départementale
- $\rho_r$ : la corrélation régionale 
- $K(\rho_d,\rho_r)$ : le noyau de corrélation

</details>


La figure suivante résume le passage d'un scénario national aux résultats des
501 circonscriptions, puis à une projection nationale en sièges :
<figure>
<img src="/figures/simulation-pipeline.svg"
     alt="Illustration du procesus complet de simulation." />
</figure>

Tout le modèle tient dans un fichier de configuration qui peut être aisément changé si vous souhaitez modifier certaines hypothèses !

<details>
<summary> Le fichier de configuration du modèle </summary>

```yaml
seed: 20240707
n_simulations: 2000
default_model: kernel_anchored

priors:
  non_expressed_retention_beta: [8.0, 2.0]
  non_expressed_tilt_uniform: [-1.0, 1.0]
  qualified_demobilisation_beta: [2.0, 38.0]
  mixing_beta: [4, 2.0]
  department_correlation_beta: [4.0, 3.0]
  region_correlation_beta: [2.0, 5.0]
  dirichlet_alpha_bounds: [0.5, 1.0]
expressed_share:
  expected_change_pts: 0.0
  national_band_pts: 10.0
  district_band_pts: 4.0

free_targets: [DIV]

transfer_orderings:
  ENS+:
    - [DVG, DVD, LR, NFP+]
    - [RN+, NON_EXPRIMES]
  NFP+:
    - [DVG]
    - [ENS+]
    - [LR, DVD]
    - [RN+, NON_EXPRIMES]
  LR:
    - [DVD, ENS+]
    - [RN+, NFP+, DVG, NON_EXPRIMES]
  RN+:
    - [LR, DVD]
    - [ENS+, NFP+, DVG, NON_EXPRIMES]
  DVG:
    - [NFP+]
    - [ENS+]
    - [LR, DVD]
    - [RN+, NON_EXPRIMES]
  DVD:
    - [LR, ENS+]
    - [RN+, NFP+, DVG, NON_EXPRIMES]
  DIV:
    - [ENS+, LR, NFP+, RN+, DVG, DVD, NON_EXPRIMES]
```

</details>

> **À RETENIR**
>
> Deux modèles plus complexes ont été développés : l'un repose sur un ancrage de la participation de chaque circonscription sur celle du premier tour, le deuxième inclut en plus une corrélation entre les circonscriptions d'un même département.
>
> Le modèle local introduit une composante locale tout en conservant également une composante nationale ; un coefficient de mélange $\lambda$ définit le poids de chacune de ces composantes.

| Modèle | Idée |
| --- | ---|
| National | Comportement identiques dans toute la France |
| National ancré | Participation liée à celle du premier tour |
| Local ancré | Ajout de variations géographiques corrélées |


## Résultats

_Tous les résultats présentés sont obtenus avec $N=3\,000$ simulations. Lorsque les résultats d'un seul modèle sont montrés, ceux-ci correspondent au modèle `local_ancré` sauf mention contraire._

Pour rendre les résultats plus interprétables, je compare les trois modèles à un modèle de référence très naïf appelé `référence` qui se contente d'attribuer une circonscription au candidat étant arrivé en tête au premier tour.


### Nombre de sièges par groupe politique

La figure ci-dessous résume les projections obtenues par les trois variantes de modèle (`national`, `national_ancré` et `local_ancré`). On constate que les résultats réels tombent dans les intervalles prédictifs marginaux à 90 %, avec un nombre de sièges pour `NFP+` qui est surestimé et `ENS+` qui est sous-estimé. L'ajout de la corrélation locale réduit l'incertitude de l'intervalle prédictif.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/seat-results-dark.svg" />
  <img src="/figures/seat-results.svg"
       alt="Intervalles de prédiction centraux à 50 et 90 % du nombre de sièges par groupe politique. Les modèles `national`, `national_ancré` et `local_ancré` sont empilés verticalement ; les points colorés indiquent les médianes, les croix grises la référence naïve, et les lignes pointillées et losanges noirs le résultat réel de 2024." />
  </picture>
  <figcaption>
    Le trait fin représente l'intervalle de prédiction central à 90 % et le trait
    épais l'intervalle central à 50 %. Le point est la médiane marginale ; le
    croix grise correspond à la règle de référence « tête au premier tour » ;
    elle n'a pas d'intervalle puisqu'elle ne modélise aucune incertitude. Le
    losange noir et la ligne verticale pointillée indiquent le résultat réel des élections.
    Les trois variantes et la référence sont empilées par groupe.
  </figcaption>
</figure>

### Évaluation détaillée des prévisions
#### Quel parti obtient une majorité relative ?
En analysant chacun des scénarios simulés, il est possible de calculer des statistiques agrégées, par exemple sur le parti arrivant en tête en moyenne.
<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/dominant-party-dark.svg" />
  <img src="/figures/dominant-party.svg"
       alt="Probabilité que NFP+, RN+ ou ENS+ soit le groupe disposant du plus grand nombre de sièges, sous le modèle national ancré, les égalités étant comptées à part." />
  </picture>
  <figcaption>
    Probabilité prédictive d'être l'unique premier groupe en nombre de sièges,
    sous <code>national ancré</code>.
  </figcaption>
</figure>

#### Effet de l'ancrage de la part de suffrages exprimés

On peut vérifier directement la valeur ajoutée par l'ajout de certains paramètres dans le modèle, comme la nouvelle modélisation des suffrages exprimés avec l'ancre.
Les deux modèles l'utilisant (`national_ancré` et `local_ancré`) prévoient nettement mieux
la part de suffrages exprimés : l'erreur médiane par circonscription passe de 3,1 à 1,9
point sans noyau de corrélation, et de 3,4 à 2,1 avec. C'est le gain le plus net du
billet — mais il porte sur la participation seule, et non sur la projection en sièges,
comme le montre le plan croisé plus bas.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/district-expressed-error-dark.svg" />
    <img src="/figures/district-expressed-error.svg"
         alt="Histogrammes des erreurs médianes de part de suffrages exprimés dans les 501 circonscriptions, pour les modèles national, national ancré et local ancré." />
  </picture>
  <figcaption>
    Pour chaque circonscription, l'erreur est la valeur absolue de la différence entre la médiane prédictive et la part réellement observée au second tour, en points de pourcentage des inscrits.
  </figcaption>
</figure>

#### Métriques de couverture et de finesse des intervalles prédictifs

Comme évoqué au début de l'article, l'évaluation quantitative de la qualité de prédiction d'un modèle peut être réalisée avec des métriques telles que l'_energy score_. 
<details>
<summary>Calcul de l'<i>energy score</i></summary>

Source : [Wikipedia](https://en.wikipedia.org/wiki/Scoring_rule#Energy_score)

Pour une distribution prédictive $D$, un résultat observé $y$, l'_energy score_ est

$$
ES(D,y)=\mathbb E_{X\sim D}\lVert X-y\rVert
-\frac12\mathbb E_{X,X'\sim D}\lVert X-X'\rVert.
$$

Le premier terme récompense la proximité avec le résultat ; le second tient
compte de la dispersion propre de la distribution. 
Ces deux composantes font que l'energy score est une méthode de _scoring_ dite "propre" : ni une concentration artificielle ni une
dispersion sans limite n'améliorent systématiquement le score. Plus il est
faible, meilleure est la prévision. Dans ce
billet, la norme euclidienne est appliquée au vecteur joint des sept nombres de
sièges.

Les espérances sont estimées par un estimateur sans biais sur les $n$
tirages $X_1,\dots,X_n$ de la simulation :

$$
\widehat{ES}=\frac1n\sum_{i=1}^{n}\lVert X_i-y\rVert
\;-\;\frac{1}{n(n-1)}\sum_{i<j}\lVert X_i-X_j\rVert .
$$

Avec une seule élection observée, ce score reste un diagnostic comparatif,
pas une preuve de supériorité générale.
</details>


Les quatre variantes correspondent aux identifiants `national`, `national_anchored`,
`kernel` (local) et `kernel_anchored` (local_ancré) du dépôt.

Le scénario de référence qui n'utilise aucun report (dans chaque circonscription, le candidat
qualifié arrivé en tête au premier tour est déclaré vainqueur du second) permet de mesurer l'apport des modèles plus complexes sur la performance de la prédiction.

| Modèle | ES national | Couverture à 90 % des scores | Largeur moyenne | Couverture à 90 % des suffrages exprimés | Suffrages exprimés nationaux | Vainqueur local correct |
| --- | --- | --- | --- | --- | --- | --- |
| _référence « vainqueur du 1er tour »_ | _185,23_ | — | — | — | — | _65,1 %_ |
| `national` | 17,98 | 75,0 % | 8,36 pts | 92,6 % | 66,5 [60,5–75,8] | 89,6 % |
| `national_anchored` | 18,42 | 76,0 % | 8,48 pts | 98,6 % | 65,0 [55,5–73,6] | 89,6 % |
| `kernel` | 15,15 | 74,7 % | 8,34 pts | 93,2 % | 66,7 [60,6–75,7] | 90,0 % |
| `kernel_anchored` | 15,61 | 76,1 % | 8,42 pts | 98,2 % | 65,3 [55,7–73,8] | 89,8 % |

Les colonnes vides de la référence ne sont pas des valeurs manquantes : cette
règle ne prédit que des vainqueurs, jamais des voix, et ne déclare aucune
incertitude. Elle n'a donc ni score de candidat, ni part de suffrages exprimés, ni
intervalle à couvrir. Elle rate 175 circonscriptions sur 501 et donne 297
sièges à `RN+` pour 143 réels : sur le vecteur de sièges, les modèles divisent son
erreur par douze.


La couverture est calculée sur les 1 091 scores de candidats qualifiés et les
501 circonscriptions de 2024.

##### Ce que chaque amélioration apporte réellement

La **dépendance entre circonscriptions** fait gagner environ 2,5 sièges d'energy score,
qu'elle s'ajoute au modèle nu (17,98 vs. 15,15) ou au modèle ancré (18,42 vs. 15,61). En
revanche elle ne change rien à la participation prévue.

L'**ancrage de la participation** fait l'inverse. Il divise par près de deux l'erreur
médiane sur la part de suffrages exprimés d'une circonscription (de 3,1 à 1,9 point en national), de (3,4 à 2,1 avec le modèle local). Mais
il ne déplace pas l'energy score de façon significative [^16].

[^16]: Le bruit Monte-Carlo se mesure en comparant une même case d'une graine à l'autre : environ 0,4 siège d'energy score avec $N=3\,000$.

##### Regard critique sur les performances du modèle

Ce tableau met en évidence que :
-  les scores des différents partis ne sont pas correctement couverts : le modèle est trop confiant sur les scores des candidats ;
- À l'inverse, il est trop prudent sur la participation estimée ; 
- La valeur ajoutée de l'ancrage est faible sur l'energy score. Cela ne signifie pas qu'il est inutile dans l'absolu mais plutôt que pour ce scrutin il n'a pas apporté des gains de précision ;
- En revanche les modèles locaux, qui s'appuient une sur une double structure nationale/locale permettent des gains de performances sur ces modèles

#### Résultats par circonscription

Un résultat remarquable est que le modèle est particulièrement bien calibré sur ce scrutin[^17] en ce qui concerne les vainqueurs au niveau des circonscriptions comme l'illustre le graphique ci-dessous. 

[^17]: Un modèle parfaitement calibré qui prédit 60% de chances qu'un parti gagne dans une circonscription aura raison dans 60% des circonscriptions où il prédit cette probabilité de victoire.

<figure class="figure-compact">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/win-probability-calibration-dark.svg" />
  <img src="/figures/win-probability-calibration.svg"
       alt="Calibration du modèle local sur le vainqueur par circonscription" />
  </picture>
  <figcaption>
  Graphique de calibration du modèle local par circonscription.
  </figcaption>
</figure>

#### Corrélations entre les sièges obtenus par parti

Le modèle montre une forte corrélation négative des sièges entre `ENS+` et `RN+`, et entre `NFP+` et `RN+` ; en d'autres termes, il y a un effet de vases communicants marqué entre ces deux partis. À l'inverse, le nombre de sièges d'`ENS+` et de `NFP+` semble presque décorrélé.
<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/joint-seats-dark.svg" />
  <img src="/figures/joint-seats.svg"
       alt="Trois projections deux à deux de la distribution prédictive jointe des sièges NFP+, ENS+ et RN+ sous le modèle local ancré." />
  </picture>
  <figcaption>
    Trois projections de la même distribution jointe sous
    <code>local ancré</code>. Les cases foncées contiennent davantage de
    simulations et le losange est le résultat réel.
  </figcaption>
</figure>

#### Impact de la part des suffrages non exprimés
La figure suivante montre que le taux d'abstention a en fait un impact relativement limité sur la répartition des sièges pour ces modèles. Une abstention élevée semble légèrement bénéficier à `ENS+` et à `NFP+` mais de manière limitée.
<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/seats-by-non-expressed-dark.svg" />
  <img src="/figures/seats-by-non-expressed.svg"
       alt="Nombre médian de sièges par parti selon la part nationale simulée de personnes n'ayant pas exprimé de suffrage valide." />
  </picture>
  <figcaption>
    Distribution prédictive a priori du modèle <code>national ancré</code>, résumée
    conditionnellement à la part de non-exprimés produite par chaque simulation.
  </figcaption>
</figure>

#### Référence : les instituts de sondage
> Avertissement
>
> Cette comparaison reste imparfaite car les regroupements de partis diffèrent, et je n'ai gardé que les blocs où l'écart est négligeable. La comparaison n'oppose donc pas tout à fait deux prévisions de même nature.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/pollster-vs-model-dark.svg" />
  <img src="/figures/pollster-vs-model.svg"
       alt="Fourchettes de sièges publiées par quatre instituts et intervalles prédictifs à 90 % des trois modèles, pour les trois blocs où les deux découpages coïncident, avec le résultat réel." />
  </picture>
  <figcaption>
    En bleu les fourchettes publiées par les instituts, en orange les intervalles
    prédictifs à 90 % des modèles, avec leur médiane ; le losange indique le
    résultat réel. Seuls figurent les trois blocs où les deux découpages
    s'accordent à trois sièges près : <code>ENS+</code> et « autres » divergent de
    15 et 19 sièges pour des raisons de nomenclature, les inclure ferait passer
    une différence de vocabulaire pour un écart de prévision. Les blocs des
    modèles sont sommés tirage par tirage avant d'en prendre les quantiles.
  </figcaption>
</figure>

Sur ce scrutin, le résultat du `RN+` est bien couvert par l'intervalle de prédiction à 90% du modèle actuel, contrairement aux fourchettes des instituts représentés. Néanmoins, les modalités de calcul des fourchettes, qui diffèrent probablement des miennes, ne permettent pas d'établir un point de comparaison quantitatif.

### Quels paramètres influencent le plus la projection ?

Les paramètres du modèle peuvent avoir deux impacts différents : certains servent surtout à rendre le modèle plus "fin" (réduire la taille des intervalles de prédiction), et d'autres servent à rendre le modèle plus "exact" dans sa prédiction médiane (faire en sorte que la prédiction médiane se rapproche le plus possible du vrai résultat). La figure suivante mesure ces deux effets sur les prédictions de sièges pour `RN+`. 

La taille des bulles représente la quantité d'information[^18] incorporée dans le paramètre via les différentes hypothèses.

[^18]: La quantité d'information est ici mesurée comme la distance à une distribution neutre (uniforme). Plus cette distance (au sens de la divergence Kullback-Leibler) est importante, plus la quantité d'information ajoutée est importante.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/parameter-influence-dark.svg" />
    <img src="/figures/parameter-influence.svg"
         alt="Carte de sensibilité des paramètres pour RN+ : leur position indique comment ils déplacent la médiane et la largeur de l'intervalle de sièges, tandis que l'aire des bulles représente l'information injectée par leur prior." />
  </picture>
  <figcaption>
    Analyse de sensibilité marginale. Chaque point représente l'effet d'un paramètre sur les sièges `RN+`.
    L'abscisse mesure l'amplitude du déplacement de leur médiane entre les dix
    déciles du paramètre ; l'ordonnée, l'amplitude de la largeur de leur intervalle
    prédictif à 90 %. Une bulle loin à droite déplace donc fortement
    la projection médiane, une bulle haute modifie fortement l'incertitude. Son
    aire représente la divergence de
    Kullback-Leibler du prior à sa référence uniforme, en bits : elle mesure la
    croyance injectée, pas son effet. Le rectangle gris central réunit les
    paramètres pour lesquels les deux amplitudes restent sous leurs planchers de
    bruit estimés par permutation.
  </figcaption>
</figure>


### Analyses a posteriori des comportements de report

Une fois l'élection passée, ces modèles peuvent être utilisés pour étudier des comportements agrégés de reports de voix _a posteriori_ (« 40 % des électeurs d'`ENS+` se sont reportés vers `NFP+` dans un duel `NFP+`/`LR` »), en s'appuyant sur les résultats réels des élections. Ces analyses permettent de dégager des tendances de fond, mais ne permettent pas de dégager des comportements individuels ou locaux, souvent mathématiquement non identifiables du fait du nombre de flux qui entrent en jeu et qui peuvent chacun se compenser, un problème connu sous le nom d'« inférence écologique ».

## Conclusion

Pouvait-on prévoir les résultats du second tour sans sondage ni historique de résultats électoraux ? Pas avec précision, mais suffisamment pour délimiter les scénarios plausibles. À partir des résultats du 1er tour et des désistements, le modèle simule les deux principales inconnues : la participation au 2nd tour et les taux de reports, en explorant différentes valeurs compatibles avec des hypothèses explicites, que j'ai voulu garder raisonnables. 

Ce choix produit naturellement des intervalles prédictifs larges, plus larges que les fourchettes publiées par les instituts de sondage, mais qui couvrent, sur ce scrutin, les résultats observés, notamment ceux du RN. 

Une information supplémentaire resserre les intervalles prédictifs. Autour de la bonne valeur si cette information est fiable, mais dans le cas contraire elle est susceptible de donner une illusion de précision. Les sondages en sont une source, mais la concordance entre les intentions de votes et les comportements réels des électeurs n'est jamais acquise, et la fiabilité de cette source n'est donc pas garantie.


L'objectif de cette expérience n'était pas de produire la prévision le plus précise mais de montrer jusqu'où mènent les données du premier tour tout en rendant visibles les hypothèses choisies et l'incertitude qu'elles génèrent. Une règle naïve consistant à attribuer chaque siège au candidat qualifié arrivé en tête au 1er tour donne 65% de circonscriptions correctes contre 90% avec le modèle. Cet écart montre que quelques hypothèses ciblées qui viennent ajouter de l'information sur des paramètres bien choisis peuvent avoir un impact significatif sur la qualité de la prédiction, sans pour autant nécessiter des modèles très complexes.

> Pour aller plus loin, vous pouvez consulter l'application [Streamlit](https://legislatives2024.vicstorm.ovh), ou le code disponible sur [GitHub](https://github.com/victor-amblard/analyse-legislatives-2024) que je vous encourage à regarder : il vous permet de modifier de nombreux paramètres (l'ordre de préférences par exemple) et d'en visualiser l'impact sur la projection.
