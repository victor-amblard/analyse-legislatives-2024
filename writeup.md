---
title: "Building a simple electoral forecasting model with minimal data"
description: "Right before the 2024 legislative elections in France, I dedicated a few days to building a simple forecasting model. Here's how it was built and why simplicity can sometimes outweigh complex and costly polls."
date: 2026-09-07
author: Victor Amblard
lang: en
---

# Could the second round of the French legislative elections be forecast without polls or historical data?

> Disclaimer 
> 
> This blog post was automatically translated from French.

_Do stated intentions predict actual votes?
Does behaviour observed in past elections still hold in the next one? These two assumptions sit at the heart of many electoral projections today._

_Can a credible forecast of legislative election results be built without them?_

_Between the two rounds of the 2024 French legislative elections, I spent a few days building a simple statistical model of the second round (refined afterwards, while trying not to let the second-round results bias me). It relies on the first-round results and the list of second-round candidates: few explicit political assumptions, no polls, no past results — and satisfying accuracy: 450 of the 501 contested seats are called correctly._

_This post is a step-by-step walkthrough of how the model was built, the methodology, its results and its limits. For the curious, the mathematical details sit in collapsible boxes._

All the model and experiment code is available [on GitHub](https://github.com/victor-amblard/analyse-legislatives-2024), and the interactive forecasts [here](https://legislatives2024.vicstorm.ovh/).

> Note: this project is above all an educational illustration of what a statistical forecasting model can do. The model was revised after the second-round results were known — not to use them, but to refine it with more time available.


## Introduction

### What political polls actually are

As an election approaches, polls and projections saturate the media. Opinion polls, which are regulated by law in France, are usually based on surveys of a _representative_ sample of a few hundred to a few thousand people asked about their voting intentions[^1].
[^1]: The definition set out in the law of 19 July 1977 reads: "_a statistical survey intended to give a quantitative indication, at a given date, of the opinions, wishes, attitudes or behaviours of a population by questioning a sample._"

Results may be published as they are, or folded into projections (in seats or in percentages), often accompanied by _margins of error_[^2] which themselves usually come from combining polls with statistical models.
[^2]: Pollsters sometimes call these margins "confidence intervals".

Between the two rounds of the 2024 legislative elections, I was struck by how narrow the published margins of error were. In the figure below, none of the last four projections published in the days before the second round contains the national result for RN+.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/pollster-intervals-dark.svg" />
  <img src="/figures/en/pollster-intervals.svg"
       alt="Seat ranges published by four polling institutes before the 2024 legislative elections, with the observed result marked for each political bloc." />
  </picture>
  <figcaption>
    Each line is the range published by one institute; the diamond marks the
    actual election result. Where a range misses that result, the dotted segment
    measures the gap. <strong>All four projections overestimated RN+ by 28 to 43
    seats.</strong> Source: data adapted from
    <a href="https://fr.wikipedia.org/wiki/Liste_de_sondages_sur_les_%C3%A9lections_l%C3%A9gislatives_fran%C3%A7aises_de_2024">Wikipedia</a>.
  </figcaption>
</figure>

A single election is of course not enough to conclude anything. The case is not isolated, though: in the 2022 legislative elections, the NUPES seat count also fell outside several published ranges.

To my mind, the problem is not that a forecast can be wrong, but that overly narrow margins of error convey false confidence. Those margins ought to represent what the statistical model cannot predict about human behaviour; instead, too much information — information that turns out _after the fact_ to be wrong — is sometimes baked into these models. Stated intentions do not reliably predict actual electoral behaviour.

### Better uncertain than falsely precise

I wanted to build a simple statistical model that relies not on what people say, but on how they have acted — and more precisely on how they have acted _recently_. No polls. No historical data.

The main challenge was to make no assumption I could not defend, to let the model adapt to the first-round data, and to draw at random everything I had no opinion about, even at the cost of being fairly uncertain.

> **Disclaimer**
>
> This post describes a personal project and does not claim to offer a general method for electoral forecasting.

### Why forecasting legislative elections is hard

Predicting the second round of French legislative elections is difficult for several reasons:

- first, the _local_ nature of the election: with one seat per constituency, local errors do not necessarily cancel out nationally, unlike in a presidential election;
- abstention is higher than in presidential elections, and non-expressed ballots are in fact the largest pool of votes going into the second round;
- candidates may withdraw between the two rounds in constituencies initially set up as three- or four-way races. The behaviour of voters whose candidate withdraws is complex.

### An unusual political context in 2024

#### An alliance of the left-wing parties

One distinctive feature of the 2024 legislative elections was the alliance of several left-wing parties known as the "Nouveau Front Populaire" (NFP), sometimes also called the "Union de la gauche". To simplify the analysis, I grouped certain official labels by affinity so as to keep only the main political forces at play, gathered into 7 categories: `NFP+`, `DVG`, `ENS+`, `LR`, `DVD`, `RN+` and `DIV`.


<details>
<summary>Mapping between official codes and the notation used in this post</summary>
The table below maps the notation used throughout this post to the official labels of the French Ministry of the Interior.

| Notation | Ministry of the Interior labels |
| --- | --- |
| NFP+ | UG, FI, ECO, SOC, RDG, VEC, COM, EXG |
| ENS+ | ENS, HOR, UDI, MDM, DVC |
| DVG | DVG |
| LR | LR |
| DVD | DVD |
| RN+ | RN, UXD, DSV, REC |
| DIV | DIV, REG |

With these conventions, the official results are as follows:
<figure>

Of the 577 constituencies, 76 were decided in the first round.

| Round | NFP+ | DVG | ENS+ | LR | DVD | RN+ | DIV | _Total_ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Round 1 | 32 | 0 | 2 | 1 | 2 | 39 | 0 | _76_ |
| Round 2 | 149 | 12  | 163 | 38 | 25 | 104 | 10 | _501_ |
| Total | 181 | 12 | 165 | 39 | 27 | 143 | 10 | _577_ |

  <figcaption>
  Table 1. Seats won by political bloc, from Ministry of the Interior data.

  </figcaption>
</figure>
</details>

#### A "republican front" that led to many withdrawals
The other distinctive feature was the withdrawal of a large number of candidates between the two rounds, notably from the `NFP+` and `ENS+` blocs, as the figure below shows:

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/withdrawals-dark.svg" />
  <img src="/figures/en/withdrawals.svg"
       alt="Number of candidates initially qualified for the second round, split between those who actually stood and those who withdrew, for each political family." />
  </picture>
  <figcaption>
    Withdrawals are heavily concentrated among NFP+ and ENS+, which turns the
    corresponding first-round votes into transfer pools that have to be modelled.
  </figcaption>
</figure>

## Building a forecasting model from scratch

### What is a forecasting model for?

Broadly speaking, a forecasting model tries to estimate a quantity $Y$ (a temperature, a share price, an election result) from input data $X$. Here, the goal is to forecast the number of seats won by each bloc, $Y$, from the first-round results, $X$.

Rather than predicting a single number, one often tries to predict a _probability distribution_, which yields what is called a "_prediction interval_"[^3] and captures the model's uncertainty.
So what we estimate is $p(Y\mid X)$, the distribution of possible values of $Y$ given $X$.
A model can return a point forecast — the median, say — or a predictive region $I$ such that
$$P(Y \in I \mid X) = 0.9$$. In practice this region is usually presented as intervals, for example: "RN+ will win between 130 and 200 seats"[^4].

[^3]: Also (incorrectly) called a "confidence interval".

[^4]: Presenting it as a product of intervals $I_{NFP+}\times\cdots\times I_{RN+}$ is not strictly equivalent to a joint region $I$, because it treats each bloc's predictive interval separately.

#### Aside: how assumptions enter a model

As we will see below, the models rely on _parameters_ that control certain quantities (the second-round abstention rate, for instance). A parameter is not in itself a source of information, but rather a lever the model uses to produce its predictions.

It is the probability distribution chosen for that parameter that carries information, and that encodes our assumptions or beliefs in the model. The stronger the assumption — or the more confident we are in a piece of information — the further the chosen distribution moves away from a "neutral distribution"[^5]. In this project we assume we have little information, so most parameter distributions stay close to neutral ones.

[^5]: "Neutral distribution" has no formal mathematical meaning. As a first approximation, and for intuition, think of a uniform distribution, which makes every possible value of the parameter equally likely.

### What makes an electoral forecasting model good?

The academic literature holds that a good forecasting model has two properties:

- _calibration_: observed results fall inside the predictive intervals at the stated frequency;
- _sharpness_: the predictive intervals are narrow.

A model that predicts between 0 and 577 seats for every bloc will cover the result every time, and be useless. Conversely, a forecast can be narrow and miss the result often. To evaluate the models at the end of this post I will use, among other things, a metric that combines closeness and spread: the _energy score_.

### The data: first-round results and the list of withdrawals

The main inputs are the [first-round legislative election results published by the French Ministry of the Interior](https://www.data.gouv.fr/datasets/elections-legislatives-des-30-juin-et-7-juillet-2024-resultats-definitifs-du-1er-tour), together with the list of second-round candidates, which tells us who withdrew.

After minimal processing, the main data source has 4,009 rows covering 577 constituencies. Here is the example of the first constituency of the Ain département.

| CodCirElec | Registered | Abstentions | Valid votes | CodNuaCand | GroupPol | Votes | valid_round_two |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0101 | 86,843 | 25,013 | 60,495 | `RN` | `RN+` | 23,819 | **True** |
| 0101 | 86,843 | 25,013 | 60,495 | `LR` | `LR` | 14,495 | **True** |
| 0101 | 86,843 | 25,013 | 60,495 | `UG` | `NFP+` | 14,188 | False |
| 0101 | 86,843 | 25,013 | 60,495 | `ENS` | `ENS+` | 7,063 | False |
| 0101 | 86,843 | 25,013 | 60,495 | `EXG` | `NFP+` | 419 | False |
| 0101 | 86,843 | 25,013 | 60,495 | `DSV` | `RN+` | 314 | False |
| 0101 | 86,843 | 25,013 | 60,495 | `DSV` | `RN+` | 197 | False |

The second-round results are used only to evaluate the models.

### Building the model step by step: vote accounting

For the rest of the analysis I will use the first constituency of the Ain (0101), where the second round pits the `RN+` candidate against the `LR` candidate after the `NFP+` candidate withdrew. I call a "vote pool" the votes of a candidate eliminated or withdrawn after the first round.

<figure>

| Political bloc | NFP+ | DVG | ENS+ | DVD | NON_EXPRESSED | **Total** |
| --- | --- | --- | --- | --- | --- | --- |
| Vote pool | 14,607 | 0 | 7,063 | 0 | 26,348 | 48,018 |

  <figcaption>
  Table 2. Second-round vote pools in constituency 0101, from Ministry of the Interior data.
  </figcaption>
</figure>

**The model's job is to work out how those 48,018 votes split between the two remaining candidates and the non-expressed ballots.**

#### Assumption 1: abstentions, blank and spoilt ballots form a single category

For simplicity, blank ballots, spoilt ballots and abstentions are merged into a single category called `NON_EXPRESSED`. This amounts to assuming that voters who abstain, vote blank or spoil their ballot behave identically as far as their flows towards candidates are concerned.

We also assume that no new voters are added to the electoral rolls between the two rounds.

#### A very simple first model: the "anti-RN front"

Consider a very simple "anti-RN front" model that sends every pooled vote to the party opposing RN+ (except votes from RN+ voters themselves). The result can be written as what is called a **transfer matrix**:

<figure class="flow-matrix">

| Source bloc / target | LR | RN+ | NON_EXPRESSED | **Total** |
| --- | --- | --- | --- | --- |
| LR | 100% (14,495) | 0 | 0 | 14,495 |
| RN+ | 0 | 100% (24,330) | 0 | 24,330 |
| NFP+ | 100% (14,607) | 0 | 0 | 14,607 |
| ENS+ | 100% (7,063) | 0 | 0 | 7,063 |
| NON_EXPRESSED | 0 | 0 | 100% (26,348) | 26,348 |
| **Total** | 36,165 (59.8%) | 24,330 (40.2%) | 26,348 | 86,843 |

<figcaption>
Table 3. An example transfer matrix for constituency 0101 under the "anti-RN
front" model. As in the flow diagram further down, blue marks the pools of
qualified candidates, orange the eliminated parties and grey the non-expressed
ballots. Read it as "100% of LR voters vote LR in the second round".
</figcaption>
</figure>

<figure>

Adding up these transfers gives the following predictions[^6]:

| Results | LR | RN+ | Non-expressed |
| --- | --- | --- | --- |
| Predicted by the "anti-RN front" model | 36,165 | 24,330 | 26,348 |
| Actual | 33,889 | 26,116 | 26,849 |

<figcaption>
Table 4. "Anti-RN front" model results compared with the actual results.
</figcaption>
</figure>

[^6]: The "Actual" row totals 86,854 registered voters, 11 more than the 86,843 of the first round: a few registrations were recorded between the two rounds. The gap is negligible here, but it is a reminder that the "no new registrations" assumption only holds to within a few units.

In this particular case the model is **deterministic**, because the transfer matrix is fixed[^7], which means it always returns the same result.

[^7]: Here all probabilities are 0 or 1. With intermediate probabilities, the multinomial draw would add individual-level variability, generally small compared with the uncertainty on the transfer rates themselves.

Such a model is of little use in the end (beyond introducing the idea of a transfer matrix): it rests on extremely strong assumptions that are generally false — that 100% of transfers go to LR.

> **KEY POINTS**
>
> - The goal of the electoral forecasting model is to predict a transfer probability matrix $T$ which determines, among other things, where the votes of eliminated candidates go.
> - The largest pool of votes is not a party, but the non-expressed ballots.
> - The model does not predict **one** transfer matrix, but a **distribution** of transfer matrices, which is what yields a predictive interval.

## Determining the transfer probability matrices

There is no way to know the transfer matrix $T$ exactly[^8]. Rather than fixing its cells arbitrarily, the usual approach is to define a distribution $p(T)$ over the possible matrices. The model becomes _probabilistic_ and explicitly represents the uncertainty about transfers. The nature of $p(T)$ depends on the assumptions made about transfers.
[^8]: It is what is called a _latent variable_.

### How should the transfer matrix distribution be set?

Three families of flows appear in the transfer matrix:

- flows from an eliminated party to a qualified party;
- flows from a qualified party to itself;
- flows into and out of the non-expressed category.

<figure>
  <img src="/figures/en/turnout-flows.svg"
       alt="Diagram of the flows between qualified parties, eliminated parties and non-expressed ballots across the two rounds: loyalty, transfers, demobilisation, mobilisation and retention." />
  <figcaption>
    Voters of a qualified candidate can stay loyal or demobilise. Voters of an
    eliminated party transfer to a qualified candidate or to the non-expressed
    category; the latter can in turn mobilise or stay non-expressed.
  </figcaption>
</figure>



Three (non-exclusive) methods can be used to set the distribution of transfer probabilities:

1. Poll voters about their voting intentions given the party they chose in the first round.


2. Analyse the results of previous elections. As we will see later, aggregate results do not allow these matrices to be recovered straightforwardly _after the fact_[^9].

[^9]: This family of problems is known as "ecological inference".

The first two methods make it possible to estimate the means and standard deviations of the transfer probabilities from a party A to a party B. Once those are estimated, each row of the matrix can be varied around the polled values by defining a probability distribution over rows. But this relies on polls or on past election results — precisely the two data sources I do not want to use.



3. The last method is to state simple assumptions about the transfer rates and derive a distribution over the matrix from them. This is the direction I chose.


Rather than relying on historical rates or on rates estimated from polls, I will define a set of constraints on preferences.
### Flow 1: transfer from an eliminated party to a qualified party

#### Assumption 2: partial orderings of transfer preferences

I keep only minimal preferences that I judge consensual enough. Several destinations therefore remain tied. This does not mean, for instance, that NFP+ voters are as willing to abstain as to vote RN+ — only that I do not want to impose an ordering between them without firmer information.
<figure>
  <img src="/figures/en/preference-orderings.svg"
       alt="Declared preference orderings for each political bloc's transfers, from most to least preferred destination." />
  <figcaption>
    Each row is a source bloc; destinations run from most to least preferred.
    Underlined items are tied: the model refuses to order them and draws their
    relative order afresh in each simulation. The constraints are deliberately
    minimal — for <code>ENS+</code> voters, the model only asserts that the
    first-tier destinations are preferred to <code>RN+</code>. For
    <code>DIV</code> it declares no ordering at all, given how heterogeneous that
    group is.
  </figcaption>
</figure>

> Note
>
> The assumption that a total preference ordering between parties can be defined and holds in every circumstance is debatable. In practice, the distinctive feature of the 2024 legislative elections was the formation of coalitions against RN+, which probably produced different preferences depending on whether RN+ was present in the constituency.

#### Turning preferences into transfer probabilities

Back to constituency 0101: the task is to turn these preferences into probabilities that can be written into the matrix $T$. I write $t_{i,j}$ for the share of party $i$'s source pool sent to party $j$. In the formulas, $\mathrm{NE}$ abbreviates non-expressed ballots.

<details>
<summary>The transfer matrix in detail</summary>

$$
T
=
\begin{array}{c|ccccccc}
\text{Source}\backslash\text{Target}
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

For the `ENS+` pool (second row), the assumed preferences require a transfer rate to `LR` higher than the rate to `RN+`. With no further assumption, we need a probability distribution that can draw any combination of transfer rates satisfying $t_{\mathrm{ENS+},\mathrm{LR}} > t_{\mathrm{ENS+},\mathrm{RN+}}$. A slightly modified _Dirichlet_ distribution[^10] does the job.
[^10]: The Dirichlet distribution is a natural choice for modelling a set of probabilities. It lets you control the mean and the spread of the sampled probabilities while keeping their sum equal to 1.

<details>
<summary>The chosen Dirichlet distribution in detail</summary>
A row of the matrix is a split of a single pool: its components are positive and
sum to 1. The model therefore draws an independent Gamma weight per destination,
then divides each weight by their sum. This standard construction yields exactly
a symmetric Dirichlet distribution: it enforces the sum constraint without
drawing and then separately correcting each cell.

The Dirichlet on its own, however, encodes **no preference**. The model sorts the
resulting shares, assigns the largest to the first preference tier and the next
ones to the second. Within a tier the assignment is drawn at random, so two
families left tied are not silently separated.

One choice remains: the shared concentration $\alpha$. It does not set the mean
of the destinations — symmetric before ranking — but the shape of the splits: a
small value favours a few very unequal shares, a large value favours shares close
to one another.

Taking $\alpha=1$ might look like the default choice; it is already an
assumption, because that value samples uniformly over all possible splits before
the ordering is applied.

The ordinal constraint imposes no minimum gap: saying that `ENS+` prefers `LR` to `RN+` says nothing about whether their transfer rates differ by 2 points or by 20. So I make an additional assumption, deliberately weak but real: very close splits are slightly less plausible than sharper ones.

Rather than fixing $\alpha=1$, I therefore let $\alpha$ vary over $\left[0.5, 1\right]$. Since it is a scale parameter, I give equal weight to multiplicative ratios by using a log-uniform law:

For each simulation, a single national $\alpha$ is drawn from

$$\log\alpha \sim \mathcal U(\log(0.5),\log 1).$$
The theoretical effect of $\alpha$

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/dirichlet-simplex-dark.svg" />
    <img src="/figures/en/dirichlet-simplex.svg"
         alt="Theoretical densities of the ENS+ transfer rates to LR and RN+ in an ordered two-destination split, for alpha equal to 0.5, 0.75 and 1." />
  </picture>
  <figcaption>
    To isolate the role of $\alpha$, this figure temporarily simplifies the
    <code>ENS+</code> row to two complementary destinations. Two Gamma variables
    are normalised; the larger share goes to <code>LR</code> and the smaller to
    <code>RN+</code>. The two theoretical densities are therefore symmetric about
    50%, and the constraint
    $t_{\mathrm{ENS+},\mathrm{LR}}>t_{\mathrm{ENS+},\mathrm{RN+}}$ always holds.
    The smaller $\alpha$ is, the more likely transfers close to 0% or 100%
    become. In the full model the non-expressed ballots are a third destination,
    so the two marginal distributions are no longer exactly symmetric.
  </figcaption>
</figure>
</details>

In practice, even though no explicit transfer rate is ever set — which is the point of this model — the choice of ordering and of distribution mechanically induces a distribution over the transfer rates, and that distribution can be visualised. The figure below shows, for two different configurations, the transfer rates implied by the partial preference ordering.
<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/prior-transfer-composition-dark.svg" />
    <img src="/figures/en/prior-transfer-composition.svg"
         alt="Prior predictive distribution of vote transfers in ENS+/RN+ and NFP+/RN+ run-offs, by source political pool." />
  </picture>
  <figcaption>
    The prior predictive distribution for two kinds of run-off (ENS+/RN+ and
    NFP+/RN+). It shows the transfer rates the model "deduces" from the imposed
    partial preference ordering.
  </figcaption>
</figure>

### Flow 2: qualified party to itself, and demobilisation

#### Assumption 3: voters of a qualified candidate may demobilise, but not vote for another candidate

There is no a priori reason for every voter who backed a qualified candidate in the first round to vote for them again in the second. I therefore assume such a voter may demobilise (cast no valid ballot), with low probability, but not vote for the other candidate.

A national demobilisation rate $d$ is drawn once per simulation and shared by all qualified candidates. Since the true rate is unknown, we give it a probability distribution with a fairly wide predictive interval, while assuming it is unlikely that more than 10% of a qualified party's voters demobilise.

<details>
<summary>Hyperparameters of the demobilisation rate</summary>
The prior is a beta distribution with a very low mean (5%) and a central 90% interval of $\left[0.9\,\%, 11.7\,\%\right]$.

$$
d\sim\operatorname{Beta}(2,38).
$$

To separate the effect of the demobilisation level from that of the spread of its
prior, I then fix $d$ at five values between 0% and 20%. The other parameters
continue to be drawn as usual.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/demobilisation-sensitivity-dark.svg" />
    <img src="/figures/en/demobilisation-sensitivity.svg"
         alt="Predictive seat intervals per political family when the national demobilisation rate is fixed successively at 0, 5, 10, 15 and 20%." />
  </picture>
  <figcaption>
    Median and central 90% predictive interval under the national anchored model,
    for 2,000 simulations per value of $d$. No second-round result is used. The
    horizontal scales differ between panels so that movements of the smaller
    blocs remain visible. The value $d=0$ serves as an experimental reference; it
    is not the prior actually used.
  </figcaption>
</figure>

The intervals overlap heavily, even across this deliberately wide grid. Between
$d=0$ and $d=20\,\%$, the median goes from 173 to 163 seats for `RN+`, from 145.5
to 150.5 for `ENS+` and from 203 to 205 for `NFP+`. Strong demobilisation does
reduce the advantage `RN+` gained in the first round, but its effect on the
centre of the prediction stays small relative to the total uncertainty. The
`RN+` interval widens more: from 132 to 150 seats. Within the range covered by
the chosen prior — essentially 1% to 12% — the differences are smaller still.
</details>

In the end, the net inflow of voters for a qualified party, say `RN+`, is the sum of RN+ voters who did not demobilise, voters from eliminated parties who transfer to RN+ (see the previous section), and people who abstained in the first round and mobilise for RN+ (see the next section).

So in constituency 0101, taking $d=0.1$ for example, the number of RN+ voters in the second round is:
$$
V_{RN+, 0101} = \underbrace{90\,\%}_{\text{10\,\% demobilisation}}\times\underbrace{24330}_{\text{RN+ voters in round 1}} + \text{transfers from other parties}
$$

The higher the demobilisation rate, the less the first-round lead weighs relative to vote transfers.

### Flow 3: to and from the non-expressed ballots

Modelling non-expressed ballots is crucial, because they are the largest pool of votes. Projections can therefore be particularly sensitive to how their evolution is represented.

The share of valid votes is hard to model, because it results from the combination of at least three things:

- the configuration of the constituency: two-, three- or four-way race;
- the identity of the qualified candidates;
- external factors, the weather for instance.

While most people who cast no valid ballot in the first round stay in that category, some vote in the second. Conversely, voters of qualified or eliminated parties may stop casting a valid ballot.


#### Assumption 4: the number of "new voters" is proportional to the non-expressed pool

Implicitly, the model assumes that a proportion — set by the transfer matrix — of the people who cast no valid ballot in the first round will cast one in the second.

This means that the larger the non-expressed pool in the first round, the larger the absolute number of people who may mobilise in the second.

The assumption simplifies the model but is hard to defend. A more flexible variant is introduced later.

What remains is to split the newly mobilised non-expressed voters between the qualified candidates.

#### Splitting new voters between parties
I deliberately made very few assumptions about how new voters (first-round abstainers, for instance) split. It is hard to know whether these voters:
- split equally between the two second-round candidates;
- split in proportion to the first-round scores;
- or, conversely, seek to support the candidate who trailed in the first round.

#### Assumption 5: no privileged split for re-mobilisation
To model these possibilities I introduced a national parameter called the _tilt_, which governs how the pool of new voters is split. Depending on its value it sends them preferentially to the leading candidate, to the trailing candidate, or splits them evenly — each with equal probability.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/tilt-effect-dark.svg" />
    <img src="/figures/en/tilt-effect.svg"
         alt="Split of mobilising non-expressed ballots between two candidates, for two first-round balances of power and three values of the tilt." />
  </picture>
  <figcaption>
    The share allocated to candidate $k$ is proportional to $s_k^{\tau}$, where
    $s_k$ is their score among the two finalists in the first round. For
    $\tau=-1$ the trailing candidate is favoured; for $\tau=0$ the flow is split
    evenly; for $\tau=1$ it exactly reproduces the first-round balance of power.
    The current prior draws $\tau$ uniformly between $-1$ and $1$, once per
    simulation.
  </figcaption>
</figure>


#### Putting it all together

To follow one scenario through to its result, take a draw where $\alpha=0.70$, the demobilisation rate is 4%, the retention of non-expressed ballots is 90% and the tilt is 0.

The figure below shows where that draw sits within each parameter's probability distribution. It also shows that $\alpha$ and $\tau$ carry little information (they are close to a neutral distribution), whereas $t_{NE,NE}$, the retention rate, and above all $d$, the demobilisation rate, carry considerably more. That information is not backed by polls or historical analysis, but rather by common sense and, at times, intuition.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/simulation-parameter-draws-dark.svg" />
    <img src="/figures/en/simulation-parameter-draws.svg"
         alt="Prior densities of the concentration, the demobilisation, the retention of non-expressed ballots and the tilt, each showing the value used in the worked example." />
  </picture>
  <figcaption>
    The four variables are drawn once, nationally. Curve heights are not
    comparable across panels: each prior has its own scale.
  </figcaption>
</figure>

##### 1. Drawing flow 1 (eliminated parties -> qualified parties + abstention)
Applying the three families of flows to constituency 0101: after the `NFP+` candidate withdrew, the second round pits `LR` against `RN+`. The 14,607 `NFP+` votes and the 7,063 `ENS+` votes form two eliminated pools. The relevant row for the first is

$$
T_{\mathrm{NFP+}}=(t_{\mathrm{NFP+},\mathrm{LR}},\ t_{\mathrm{NFP+},\mathrm{RN+}},\
t_{\mathrm{NFP+},\mathrm{NE}}).
$$

The declared ordering simply becomes

$$LR \succ \{RN+,\mathrm{NON\_EXPRESSED}\}.$$

The model starts by drawing a total preference ordering at random, say $LR \succ RN+ \succ \text{NON\_EXPRESSED}$, then draws transfer rates compatible with that total ordering from the enhanced Dirichlet distribution.
It might, for example, allocate 62% of the `NFP+` votes to `LR`, 25% to `RN+` and 13% to non-expressed. It proceeds the same way for the `ENS+` votes. This gives:
<figure>

| Source bloc / target | LR | RN+ | NON_EXPRESSED | **Total** |
| --- | --- | --- | --- | --- |
| NFP+ | 62% | 25% | 13% | 100% |
| ENS+ | 71% | 19% | 10% | 100% |
<figcaption>
Flow 1 for constituency 0101
</figcaption>
</figure>

##### 2. Drawing flow 2 (qualified parties -> qualified parties + abstention)

Next, the model draws a demobilisation rate, 4% say, which gives:
<figure>

| Source bloc / target | LR | RN+ | NON_EXPRESSED | **Total** |
| --- | --- | --- | --- | --- |
| LR | 96% | 0% | 4% | 100% |
| RN+ | 0% | 96% | 4% | 100% |
<figcaption>
Flow 2 for constituency 0101
</figcaption>
</figure>

##### 3. Drawing flow 3 (`NON_EXPRESSED` -> all parties)
Then we draw a 90% retention rate for non-expressed ballots and a tilt of 0. This means the 10% of first-round abstainers who re-mobilise are split evenly between the candidates:
<figure>

| Source bloc / target | LR | RN+ | NON_EXPRESSED | **Total** |
| --- | --- | --- | --- | --- |
| NON_EXPRESSED | 5% | 5% | 90% | 100% |
<figcaption>
Flow 3 for constituency 0101
</figcaption>
</figure>

##### The complete sampled transfer matrix
<figure class="flow-matrix">

| Source bloc / target | LR | RN+ | NON_EXPRESSED | **Total** |
| --- | --- | --- | --- | --- |
| LR | 96% | 0% | 4% | 100% |
| RN+ | 0% | 96% | 4% | 100% |
| NFP+ | 62% | 25% | 13% | 100% |
| ENS+ | 71% | 19% | 10% | 100% |
| NON_EXPRESSED | 5% | 5% | 90% | 100% |
</figure>

##### The specific case of constituency 0101
Taking the various vote pools into account gives the following transfers.

The 24,330 `RN+` votes here combine the 23,819 votes of the qualified candidate
and the 511 votes (314 + 197) of two other candidates from the same political
family, following the aggregation the model uses.

<figure class="flow-matrix">

| Source bloc / target | LR | RN+ | NON_EXPRESSED | **Total** |
| --- | --- | --- | --- | --- |
| LR | 13,915 | 0 | 580 | 14,495 |
| RN+ | 0 | 23,357 | 973 | 24,330 |
| NFP+ | 9,056 | 3,652 | 1,899 | 14,607 |
| ENS+ | 5,015 | 1,342 | 706 | 7,063 |
| NON_EXPRESSED | 1,317 | 1,317 | 23,714 | 26,348 |
| Total | **29,303** | **29,668** | **27,872** | **86,843** |
</figure>

The same draw can be shown as a flow diagram:
<figure>
  <img src="/figures/en/prior-sankey.svg"
       alt="Flow diagram of the illustrative draw in constituency 0101, from the first to the second round." />
  <figcaption>
    Ribbon width represents a number of votes, not a transfer rate. The figure
    reuses the first-round pools and the rates drawn in the three steps above; it
    shows only one possible simulation.
  </figcaption>
</figure>


### Scaling up to the whole country
So far I have used a single constituency. How should the model be extended to the 501 constituencies to be predicted?

#### Assumption 6: no local variation

For this first model I assume transfer preferences are uniform across France. That is, the probability that an NFP+ voter transfers to ENS+ is the same in the Ain as in Paris. As a result, a single matrix $T$ is used for the whole country.

So there is only one transfer matrix to predict, reused by every constituency.
This assumption is fairly unrealistic; I will show later how to adapt the model to local variation.

> **KEY POINTS**
>
> - The model never declares transfer rates, only partial orderings of preference between transfers.
> - Those orderings mechanically induce constraints on the possible transfer rates, while leaving uncertainty in place.
> - As an example, in an NFP+/RN+ run-off the model estimates the ENS+ to NFP+ transfer rate at between 46% and 98% (at the 90% level).

<details>
<summary>Mathematical summary of the model</summary>
The model estimates $Y$, the number of seats per party, from $X$, the first-round
results.
It relies on two national _latent_ variables — the transfer matrix $T$ and the
demobilisation rate $d$ — plus a parameter $\alpha$, also unknown, that governs
the conversion of preferences into probabilities. Write $\Theta=(T,d,\alpha)$ for
the three together.

Being probabilistic, what the model estimates is a distribution:

$$
p(Y \mid X) = \int p(Y \mid \Theta, X)\, p(\Theta \mid X)\, d\Theta
$$

For this first model, the transfer matrix distribution does not use the
first-round results: $p(\Theta \mid X) = p(\Theta)$, and

$$
p(Y \mid X) = \int p(Y \mid \Theta, X)\, p(\Theta)\, d\Theta
$$

The first factor, $p(\Theta)$, is the distribution described in the sections
above:
$$
p(\Theta) = p(T,d,\alpha) = p(\alpha)p(d)p(T|d,\alpha)

$$

The second, $p(Y \mid X,\Theta)$, is the step from transfer rates to seat counts —
almost pure arithmetic:
$$
p(Y|X) = \int p(\alpha)p(d)p(T|d,\alpha)p(Y|T,X) d\alpha dd dT
$$

Writing $T_c=(t_{c,i,j})_{i,j}$ for the matrix adapted to constituency $c$ and
$n_{c,i}$ for the size of party $i$'s pool, the vector of transfers from that pool
to all destinations follows a multinomial law:

$$
R_{c,i}\sim\mathcal{M}\left(n_{c,i},\ t_{c,i,\cdot}\right)
$$

The constituency's vote vector is the sum of these transfers:

$$
V_c = \sum_{i} R_{c, i}
$$

And party $i$'s seat count is the number of constituencies it wins:

$$
Y_i = \sum_{c} \mathbf{1}\left[\arg\max V_c = i\right]
$$

Almost all of the uncertainty comes from the first factor; the second is close to
deterministic.
</details>

Across many draws, the predictive distribution gradually emerges:

<figure>
  <picture>
    <source media="(prefers-reduced-motion: reduce) and (prefers-color-scheme: dark)" srcset="/figures/en/district-0101-simulations-dark.png" />
    <source media="(prefers-reduced-motion: reduce)" srcset="/figures/en/district-0101-simulations.png" />
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/district-0101-simulations-dark.gif" />
    <img src="/figures/en/district-0101-simulations.gif"
         alt="Animation of 20,000 simulations of constituency 0101: each point shows the LR and RN+ shares of registered voters, while the cumulative frequency of an LR win stabilises." />
  </picture>
  <figcaption>
    Each point is one simulated second round in constituency 0101. The two axes
    give the LR and RN+ shares of registered voters; the diagonals indicate the
    complementary share of non-expressed ballots. The frequency shown is
    recomputed after each batch of draws.
  </figcaption>
</figure>

<details>
<summary>Formal details of the simulation</summary>
The simulation follows naturally from the decomposition of $p(Y\mid X)$ described above:

- sample the transfer rates $T\sim p(T)$;
- draw the national demobilisation rate $d\sim\operatorname{Beta}(2,38)$;
- for each constituency, adapt $T$ to the qualified candidates and their demobilisation to obtain $T_c$;
- run a multinomial draw to allocate each bloc's vote pool;
- derive the constituency result, $V_c$;
- aggregate seats nationally to obtain $Y$.

Repeating this $N$ times gives a Monte Carlo estimate of $p(Y\mid X)$.

This yields 90% prediction intervals directly, and allows conditional analyses such as: "as the simulated share of non-expressed ballots varies, how does the seat projection move?"

</details>

### The weaknesses of this model

This model rests on two simplifying assumptions:
- behaviour is the same everywhere in France (assumption 6);
- the share of valid votes is poorly controlled (assumption 4).

The next section describes how to build a model without them.

## Towards a more complex model?

The model built so far — referred to below as the `national` model — ignores local variation and only models valid votes indirectly.

### Improvement #1: a better model of non-expressed ballots?

Modelling the retention of non-expressed ballots through the transfer-matrix parameter $t_{\mathrm{NE},\mathrm{NE}}$ (assumption 4) introduces a re-mobilisation bias in the second round.

**Example**:
Constituency 5908, in the Nord département, had a very low share of valid votes in the first round (52.1%). Drawing standard values for the various parameters shows that the current mechanism mechanically produces a fall in abstention in the second round, which there is no real reason to expect.

<figure>
  <img src="/figures/en/non-expressed-balance.svg"
       alt="Diagram of the flows between qualified parties, eliminated parties and non-expressed ballots across the two rounds: loyalty, transfers, demobilisation, mobilisation and retention." />
  <figcaption>
    Flows between qualified parties, eliminated parties and non-expressed ballots
    across the two rounds, illustrating how the national model computes them.
  </figcaption>
</figure>

Since the pool of non-expressed ballots is larger than any party's, it seemed to me essential to model the share of valid votes well in each constituency — even more so than to model transfers between parties well.

Rather than controlling a single transfer rate, a variable about which we have little information, I wanted to control the share of valid votes in the second round, constituency by constituency. That target imposes a constraint shared by all flows into the non-expressed category[^11].
[^11]: As we will see shortly, the same target can be reached by several combinations of flows.

To set the second-round share of valid votes, I take it to be the sum of the first-round share (treated as an "anchor"), a national drift between the two rounds, and a random local variation[^12].
[^12]: The sum is actually taken on the "logit" scale, which keeps the percentage between 0 and 100% without applying an identical subtraction to every constituency.

The national drift between the two rounds is typically negative: turnout in the second round is often lower than in the first. Absent more precise information, this drift is set to 0 on average and allowed to vary quite widely.

<details>
<summary> The valid-vote share equation </summary>
Write:

- $r_{c,1}$ (resp. $r_{c,2}$) for the share of valid votes in the first (resp. second) round in constituency $c$
- $\delta_{nat}$ for the national drift: if positive, there are more valid votes nationally in the second round than in the first
- $\delta_c$ for a local variation (at the level of constituency $c$)


$$
\text{logit}(r_{c,2}) = \text{logit}(r_{c,1})+\delta_{nat}+\delta_c
$$

As the diagram below shows, the controlled parameter is no longer a rate on one flow, but the net balance of all the flows that raise or lower the percentage of valid votes.
</details>
<figure>
  <img src="/figures/en/non-expressed-anchored.svg"
       alt="Diagram of the flows between qualified parties, eliminated parties and non-expressed ballots across the two rounds: loyalty, transfers, demobilisation, mobilisation and retention." />
  <figcaption>
    Flows between qualified parties, eliminated parties and non-expressed ballots
    across the two rounds, under the new way of computing the share of
    non-expressed ballots.
  </figcaption>
</figure>

#### Identifiability of the valid-vote share

The retention rate (voters non-expressed in both rounds) cannot simply be deduced from the share of valid votes, because valid votes arrive by several paths, as explained above.

<details>
<summary>How are the transfer-matrix parameters derived from it?</summary>

The target set on the share of non-expressed ballots constrains the net balance of all flows into the non-expressed category, but not where they come from. Yet the retention of non-expressed ballots, the demobilisation of qualified voters and the transfers from eliminated parties to the non-expressed category each already have a prior distribution.

The model therefore starts from a draw of all these rates, then looks for the combination compatible with the target (the share of non-expressed ballots) that departs from it least, by minimising the sum of Kullback-Leibler divergences between the probabilities before and after adjustment, weighted by the size of each vote pool. The solution amounts to applying the same shift on the logit scale to every flow into the non-expressed category simultaneously.

Transfers between candidates among the valid votes do not change: only the share going to the non-expressed category varies, and all the other shares in the row are rescaled by the same factor. The constraints from the preference orderings are also preserved. If a target lies outside the physically achievable set, it is brought back to the boundary.

This operation is a computable approximation of projecting the model's full joint law, which would require knowing the turnout density jointly induced across the 501 constituencies.
</details>

Let us now look at the valid-vote shares produced by the *prior* predictive distribution (without using any second-round result).
<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/expressed-share-dark.svg" />
    <img src="/figures/en/expressed-share.svg"
         alt="Histogram of the predictive distribution of the national share of valid votes under the national anchored model." />
  </picture>
  <figcaption>
    Prior predictive distribution of the national share of valid votes. The band
    shows the central 90% interval and the line its median. No second-round
    result enters this distribution.
  </figcaption>
</figure>

### Improvement #2: modelling local behaviour
There is no a priori reason for voter behaviour to be the same everywhere in France. A first idea to fix this would be to draw a transfer matrix $T_c$ per constituency, independently.

#### A careful blend of national trend and local specificity

#### Assumption 6B: voter behaviour = national trend + local specificity

In reality it is reasonable to assume that voter behaviour in a constituency results from a national trend plus local specificities that shift behaviour marginally away from that trend.

This naturally leads to a hierarchical structure: a national matrix shared by all constituencies, plus a local matrix specific to each one, the total transfer matrix being a blend of the two, modulated by a coefficient $\lambda$. For a constituency $c$ this can be written[^13]:

$$
T_{c} = \lambda \times T_{nat} + (1-\lambda) \times T_{local, c}
$$
[^13]: This is not exactly how the model is actually implemented.
<details>
<summary> How is the mixing coefficient $\lambda$ chosen? </summary>

The previous model (`national`) corresponds to $\lambda=1$. A fully local model would correspond to $\lambda = 0$. In practice, since its true value is unknown, $\lambda$ is drawn from a Beta(4,2) distribution. That distribution encodes our assumption that local behaviour is a marginal variation, so that values of $\lambda$ are concentrated towards the right, between 0.5 and 1, while still leaving many values possible.
</details>

#### How are local variations of the transfer matrices set?

We know local variations exist, but not their direction: we do not know, for instance, whether voters transfer more to RN+ in one constituency than in another. What we can express is a dependence structure: _"I do not know which way this constituency will deviate from the average, but a politically similar constituency will probably deviate the same way."_

The choice made is therefore to keep the same distribution for the transfer matrix in every constituency, but to give it a specific correlation structure: the local matrices are no longer independent[^14]. Introducing a correlation changes only their dependence: depending on the share of national variation and the reach of the local correlations, uncertainties can cancel out more, or on the contrary add up, in the national projections.

[^14]: The _marginal distribution_ of the matrices $T_c$ stays the same as in the previous model. In other words, taken separately, each local transfer matrix has the same law — and therefore the same statistics — as the national matrix. Taken nationally, however, some matrices move "together", which can change the results.

In the same way, the tilt — which governs how voters who mobilise in the second round after abstaining in the first split between the qualified parties — can be given the same national/local hierarchical structure with correlation.

#### Choosing the dependence structure: how are constituencies correlated?

While it is reasonable to assume transfer rates are correlated across constituencies, identifying the source of that correlation is harder. It could be:
- socio-demographic variation in the voter profile;
- political shades between candidates — an `NFP+` candidate from LFI and an `NFP+` candidate from the PS may elicit different behaviour;
- other local factors.

#### Assumption 6C: transfer rates are correlated between constituencies of the same region and the same département

Unlike the assumption of no local variation, this model allows local variation, correlated according to the constituency's département. More precisely, two constituencies in the same département are more strongly correlated than two in the same region but different départements, which are themselves more correlated than two constituencies in different regions.

<details>
<summary>The national/local blend, formally</summary>

Averaging two matrices directly would change the marginal distribution of the
transfer rates. The blend is therefore performed on a latent Gaussian scale,
before the transformation into probabilities:

$$
z_c = \sqrt{\lambda}\,z^{nat}
      + \sqrt{1-\lambda}\,z^{loc}_c,
$$

where $z^{nat}\sim\mathcal N(0,1)$ is shared by all constituencies and
$z^{loc}\sim\mathcal N(0,K)$ is a local component.

In practice $K$ is set as follows:
- $K_{c,c} = 1$
- $K_{c_{1}, c_2} = \rho_{d}$ if $c_1$ and $c_2$ are in the same département
- $K_{c_1, c_2} = \rho_{r}$ if $c_1$ and $c_2$ are in the same region but different départements
- $K_{c_1, c_2} =0$ otherwise

Since $K_{cc}=1$, each $z_c$ remains marginally distributed as $\mathcal N(0,1)$. Between two constituencies $c_1$ and $c_2$, the latent covariance is:

$$
\operatorname{Cov}(z_{c_1},z_{c_2})
=
\lambda+(1-\lambda)K_{c_1, c_2}.
$$

So taking for example $\rho_d=0.7$, $\rho_r=0.3$ and $\lambda=0.6$, the correlations are:
- within the same département: 0.88
- within the same region: 0.72
- between two different regions: 0.6 ($\lambda$)

As for drawing $z^{loc}_c$:
- for each region $r$, draw $z^R_{r}\sim\mathcal{N}(0,1)$
- for each département $d$, draw $z^D_{d}\sim\mathcal{N}(0,1)$
- for each constituency, draw $\varepsilon_c$

One can show that setting
$$
z^{loc}_c = \sqrt{\rho_r}z^R_{r(c)} + \sqrt{\rho_d-\rho_r}z^D_{d(c)}+\sqrt{1-\rho_d}\varepsilon_c
$$
yields a random variable with the required properties.
</details>
The illustration below gives an example, for one constituency, of the correlations between transfer rates within a single row of the matrix.
<figure>
  <img src="/figures/en/national-local-mixing.svg"
       alt="Effect of the mixing coefficient on one transfer row" />
  <figcaption>
Effect of the mixing coefficient lambda on transfer rates, depending on whether the constituencies are in the same département (hence correlated) or not.
  </figcaption>
</figure>

### Putting it all together
The variables drawn in one simulation of the local anchored model can now be gathered into a single view:

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/anchored-parameter-draws-dark.svg" />
    <img src="/figures/en/anchored-parameter-draws.svg"
         alt="Prior densities of the local anchored model's parameters, arranged in three rows: parameters shared with the national model, turnout-anchoring parameters, and local parameters." />
  </picture>
  <figcaption>
    In the anchored model, the retention of non-expressed ballots is drawn first,
    then adjusted jointly with the other flows into the non-expressed category.
    The two deltas are expressed on the logit scale. The distributions of
    $\rho_d$ and $\rho_r$ are those declared before the constraint
    $\rho_r\leq\rho_d$ is applied.
  </figcaption>
</figure>

### Summary of the `local anchored` model

| Assumption | Status |
| --- | --- |
|1: blank and spoilt ballots treated like abstentions | Kept |
|2: partial preference orderings | Kept |
|3: demobilisation of a qualified party's voters | Kept |
|4: number of new voters proportional to the non-expressed pool | Removed (anchor) |
|5: no privileged split for re-mobilisation | Kept |
|6: no local variation | Removed |
|6B: voter behaviour = national trend + local specificity | Added (national/local blend via $\lambda$) |
|6C: departmental and regional correlation of transfer rates | Added (kernel) |

<details>
<summary>The model's parameters in detail</summary>

As before:

$$
p(Y \mid X) = \int p(Y \mid X, \Theta)\, p(\Theta \mid X)\, d\Theta
$$

but $\Theta$ is no longer independent of $X$: the first-round results are used to compute
both the kernel **and** the turnout anchor. The conditional distribution factorises in
the order in which the simulator actually draws:

$$
p(\Theta \mid X) =
\underbrace{p(\lambda)p(\rho_d|X)p(\rho_r|X)p(\alpha)p(\delta_{nat})}_{\text{random hyperparameters}}
\;\cdot\;
\underbrace{p\!\left(r_{\cdot,2} \mid X, \delta_{nat}\right)}_{\text{turnout anchor}}
\;\cdot\;
\underbrace{p(d)p\!\left(T_c \mid K(\rho_d, \rho_r), \alpha, r_{\cdot,2}\right)}_{\text{transfer rates}}
$$
Parameter laws:

_Shared with the `national` model_
- Concentration coefficient $\alpha$: $\log(\alpha)\sim\text{LogU}(\log(0.5), \log(1))$
- Demobilisation coefficient $d\sim\operatorname{Beta}(2, 38)$

_Specific to the `national_anchored` and `local_anchored` models_

- $r_{\cdot, 2} | X, \delta_{nat} : \text{logit}(r_{\cdot, 2}) = \text{logit}(r_{\cdot, 1}) + \delta_{nat} + \delta_c$


_Specific to the `local_anchored` model_
- Mixing coefficient $\lambda\sim\operatorname{Beta}(4,2)$
- $\rho_d$: the departmental correlation
- $\rho_r$: the regional correlation
- $K(\rho_d,\rho_r)$: the correlation kernel

</details>


The figure below summarises the path from a national scenario to the results of the
501 constituencies, and then to a national seat projection:
<figure>
<img src="/figures/en/simulation-pipeline.svg"
     alt="Illustration of the complete simulation process." />
</figure>

The whole model fits in one configuration file, which can easily be changed if you want to alter some of the assumptions!

<details>
<summary> The model configuration file </summary>

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

> **KEY POINTS**
>
> Two more complex models were developed: one anchors each constituency's turnout on its first-round turnout, the second additionally includes a correlation between constituencies of the same département.
>
> The local model introduces a local component while keeping a national one; a mixing coefficient $\lambda$ sets the weight of each.

| Model | Idea |
| --- | ---|
| National | Identical behaviour across the whole country |
| National anchored | Turnout tied to first-round turnout |
| Local anchored | Adds correlated geographic variation |


## Results

_All results shown use $N=3\,000$ simulations. Where a single model's results are shown, they are those of the `local_anchored` model unless stated otherwise._

To make the results easier to interpret, I compare the three models against a very naive reference model, called `reference`, which simply awards each constituency to the candidate who led in the first round.


### Seats per political bloc

The figure below summarises the projections from the three model variants (`national`, `national_anchored` and `local_anchored`). The actual results fall inside the marginal 90% predictive intervals, with `NFP+` overestimated and `ENS+` underestimated. Adding the local correlation reduces the width of the predictive interval.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/seat-results-dark.svg" />
  <img src="/figures/en/seat-results.svg"
       alt="Central 50% and 90% prediction intervals for the seat count of each political bloc. The `national`, `national_anchored` and `local_anchored` models are stacked vertically; dots mark the medians and black diamonds the actual 2024 result." />
  </picture>
  <figcaption>
    The thin line is the central 90% prediction interval and the thick line the
    central 50% interval. The dot is the marginal median; the black diamond and
    the dotted line mark the actual election result. The three variants are
    stacked within each bloc.
  </figcaption>
</figure>

### Evaluating the forecasts in detail
#### Which party wins a relative majority?
By analysing each simulated scenario, aggregate statistics can be computed — for instance on which party comes first on average.
<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/dominant-party-dark.svg" />
  <img src="/figures/en/dominant-party.svg"
       alt="Probability that NFP+, RN+ or ENS+ holds the largest number of seats under the national anchored model, with ties counted separately." />
  </picture>
  <figcaption>
    Predictive probability of being the single largest bloc by seat count, under
    <code>national anchored</code>.
  </figcaption>
</figure>

#### Effect of anchoring the valid-vote share

The value added by a given parameter can be checked directly — for instance the new way of modelling valid votes with the anchor.
The two models that use it (`national_anchored` and `local_anchored`) predict the share
of valid votes markedly better: the median error per constituency falls from 3.1 to 1.9
points without the correlation kernel, and from 3.4 to 2.1 points with it. This is the
clearest gain in the whole post — but it concerns turnout alone, not the seat
projection, as the crossed design further down shows.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/district-expressed-error-dark.svg" />
    <img src="/figures/en/district-expressed-error.svg"
         alt="Histograms of the median valid-vote-share errors across the 501 constituencies, for the national, national anchored and local anchored models." />
  </picture>
  <figcaption>
    For each constituency, the error is the absolute difference between the predictive median and the share actually observed in the second round, in percentage points of registered voters.
  </figcaption>
</figure>

#### Coverage and sharpness metrics for the predictive intervals

As mentioned at the start of this post, a model's forecasting quality can be evaluated quantitatively with metrics such as the _energy score_.
<details>
<summary>Computing the <i>energy score</i></summary>

Source: [Wikipedia](https://en.wikipedia.org/wiki/Scoring_rule#Energy_score)

For a predictive distribution $D$ and an observed result $y$, the _energy score_ is

$$
ES(D,y)=\mathbb E_{X\sim D}\lVert X-y\rVert
-\frac12\mathbb E_{X,X'\sim D}\lVert X-X'\rVert.
$$

The first term rewards closeness to the result; the second accounts for the
distribution's own spread.
Together these make the energy score a "proper" scoring rule: neither artificial
concentration nor unlimited spread systematically improves it. The lower it is,
the better the forecast. In this post the Euclidean norm is applied to the joint
vector of the seven seat counts.

The expectations are estimated by an unbiased estimator over the $n$ simulation
draws $X_1,\dots,X_n$:

$$
\widehat{ES}=\frac1n\sum_{i=1}^{n}\lVert X_i-y\rVert
\;-\;\frac{1}{n(n-1)}\sum_{i<j}\lVert X_i-X_j\rVert .
$$

With a single observed election, this score remains a comparative diagnostic, not
proof of general superiority.
</details>


The four variants correspond to the repository identifiers `national`, `national_anchored`,
`kernel` (local) and `kernel_anchored` (local anchored).

The reference scenario, which uses no transfers at all (in each constituency the qualified
candidate who led the first round is declared the second-round winner), makes it possible to measure what the more complex models actually add.

| Model | National ES | 90% coverage of scores | Mean width | 90% coverage of valid-vote share | National valid-vote share | Correct local winner |
| --- | --- | --- | --- | --- | --- | --- |
| _reference "first-round leader"_ | _185.23_ | — | — | — | — | _65.1%_ |
| `national` | 17.98 | 75.0% | 8.36 pts | 92.6% | 66.5 [60.5–75.8] | 89.6% |
| `national_anchored` | 18.42 | 76.0% | 8.48 pts | 98.6% | 65.0 [55.5–73.6] | 89.6% |
| `kernel` | 15.15 | 74.7% | 8.34 pts | 93.2% | 66.7 [60.6–75.7] | 90.0% |
| `kernel_anchored` | 15.61 | 76.1% | 8.42 pts | 98.2% | 65.3 [55.7–73.8] | 89.8% |

The reference's empty cells are not missing values: that rule predicts only winners,
never votes, and declares no uncertainty. It therefore has no candidate score, no
valid-vote share and no interval to cover[^15]. It misses 175 of the 501 constituencies
and gives `RN+` 297 seats against 143 actual: on the seat vector, the models divide its
error by twelve.

[^15]: Its energy score reduces to the Euclidean distance between its seat vector and the actual result: a deterministic forecast is a Dirac mass, whose spread term is zero. That is what allows it to sit in the same column as the simulated models.

Coverage is computed over the 1,091 scores of qualified candidates and the
501 constituencies of 2024.

##### What each improvement actually contributes

The **dependence between constituencies** is worth about 2.5 seats of energy score,
whether it is added to the bare model (17.98 vs. 15.15) or to the anchored one (18.42 vs.
15.61). It changes nothing about predicted turnout.

**Anchoring turnout** does the opposite. It nearly halves the median error on a
constituency's valid-vote share (from 3.1 to 1.9 points nationally, and from 3.4 to 2.1
with the local model). But it does not move the energy score significantly[^16].

[^16]: Monte Carlo noise can be measured by comparing the same cell across two seeds: about 0.4 seats of energy score with $N=3\,000$.

##### A critical look at the model's performance

This table shows that:
- candidate scores are not correctly covered: the model is overconfident about candidate scores;
- conversely, it is too cautious about estimated turnout;
- the value added by the anchor on the energy score is small. That does not mean it is useless in general, but rather that for this election it brought no gain in precision;
- the local models, on the other hand, which rely on a dual national/local structure, do improve performance.

#### Results by constituency

One striking result is that the model is particularly well calibrated for this election[^17] when it comes to constituency winners, as the chart below shows.

[^17]: A perfectly calibrated model that gives a party a 60% chance of winning a constituency will be right in 60% of the constituencies where it predicts that win probability.

<figure class="figure-compact">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/win-probability-calibration-dark.svg" />
  <img src="/figures/en/win-probability-calibration.svg"
       alt="Calibration of the local model on the winner in each constituency" />
  </picture>
  <figcaption>
  Calibration chart of the local model, by constituency.
  </figcaption>
</figure>

#### Correlations between the seat counts of each party

The model shows a strong negative correlation between `ENS+` and `RN+` seats, and between `NFP+` and `RN+`; in other words there is a marked communicating-vessels effect between them. By contrast, the seat counts of `ENS+` and `NFP+` appear almost uncorrelated.
<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/joint-seats-dark.svg" />
  <img src="/figures/en/joint-seats.svg"
       alt="Three pairwise projections of the joint predictive distribution of NFP+, ENS+ and RN+ seats under the local anchored model." />
  </picture>
  <figcaption>
    Three projections of the same joint distribution under
    <code>local anchored</code>. Darker cells contain more simulations and the
    diamond is the actual result. A pairwise projection does not show the whole
    seven-dimensional law, but it makes visible the dependencies that seven
    marginal intervals would hide.
  </figcaption>
</figure>

#### Impact of the share of non-expressed ballots
The figure below shows that the abstention rate in fact has a fairly limited impact on the seat distribution in these models. High abstention seems to benefit `ENS+` and `NFP+` slightly, but only mildly.
<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/seats-by-non-expressed-dark.svg" />
  <img src="/figures/en/seats-by-non-expressed.svg"
       alt="Median number of seats per party as a function of the simulated national share of people casting no valid ballot." />
  </picture>
  <figcaption>
    Prior predictive distribution of the <code>national anchored</code> model,
    summarised conditionally on the share of non-expressed ballots produced by
    each simulation.
  </figcaption>
</figure>

#### Benchmark: the polling institutes
> Disclaimer
>
> This comparison remains imperfect because the party groupings differ, and I kept only the blocs where the discrepancy is negligible. It therefore does not quite pit two forecasts of the same nature against each other.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/pollster-vs-model-dark.svg" />
  <img src="/figures/en/pollster-vs-model.svg"
       alt="Seat ranges published by four institutes and 90% predictive intervals of the three models, for the three blocs where the two groupings coincide, with the actual result." />
  </picture>
  <figcaption>
    In blue, the ranges published by the institutes; in orange, the models' 90%
    predictive intervals with their medians; the diamond marks the actual result.
    Only the three blocs where the two groupings agree to within three seats are
    shown: <code>ENS+</code> and "others" differ by 15 and 19 seats for naming
    reasons, and including them would pass off a difference in vocabulary as a
    forecasting gap. The models' blocs are summed draw by draw before quantiles
    are taken.
  </figcaption>
</figure>

For this election, the `RN+` result is well covered by the current model's 90% prediction interval, unlike the ranges of the institutes shown. That said, how those ranges are computed probably differs from my own method, so no quantitative comparison can be established.

### Which parameters influence the projection most?

The model's parameters can have two distinct effects: some mainly make the model "sharper" (narrowing the prediction intervals), others make it more "accurate" in its median prediction (bringing the median as close as possible to the true result). The figure below measures both effects on the `RN+` seat predictions.

Bubble size represents the amount of information[^18] the parameter carries through the various assumptions.

[^18]: Information is measured here as the distance to a neutral (uniform) distribution. The larger that distance — in the Kullback-Leibler sense — the more information has been added.

<figure>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/figures/en/parameter-influence-dark.svg" />
    <img src="/figures/en/parameter-influence.svg"
         alt="Parameter sensitivity map for RN+: position shows how each parameter shifts the median and the width of the seat interval, while bubble area represents the information injected by its prior." />
  </picture>
  <figcaption>
    A marginal sensitivity analysis. Each point is one parameter's effect on
    `RN+` seats. The horizontal axis measures how far the median moves across the
    parameter's ten deciles; the vertical axis, how much the width of the 90%
    predictive interval changes. A bubble far to the right therefore shifts the
    median projection strongly; a high bubble strongly changes the uncertainty.
    Its area is the Kullback-Leibler divergence of the prior from its uniform
    reference, in bits: it measures the belief injected, not its effect. The grey
    rectangle in the middle gathers the parameters for which both amplitudes stay
    below their noise floors, estimated by permutation.
  </figcaption>
</figure>


### Post-hoc analysis of transfer behaviour

Once the election is over, these models can be used to study aggregate vote-transfer behaviour _after the fact_ ("40% of `ENS+` voters transferred to `NFP+` in an `NFP+`/`LR` run-off"), using the actual results. Such analyses can reveal broad trends, but not individual or local behaviour, which is often mathematically unidentifiable given the number of flows involved and the fact that they can offset one another — a problem known as "ecological inference".

## Conclusion

Could the second-round results be forecast without polls or a history of past election results? Not precisely, but well enough to delimit the plausible scenarios. From the first-round results and the withdrawals, the model simulates the two main unknowns — second-round turnout and transfer rates — exploring the values compatible with explicit assumptions that I tried to keep reasonable.

That choice naturally produces wide predictive intervals, wider than the ranges published by the polling institutes, but which do cover the observed results for this election, RN's in particular.

Additional information narrows the predictive intervals. Around the right value if that information is reliable — but otherwise it can create an illusion of precision. Polls are one such source, yet the match between stated voting intentions and voters' actual behaviour is never guaranteed, so the reliability of that source is not guaranteed either.


The aim of this experiment was not to produce the most precise forecast, but to show how far the first-round data alone can take us, while making visible the assumptions chosen and the uncertainty they generate. A naive rule awarding each seat to the qualified candidate who led the first round gets 65% of constituencies right, against 90% for the model. That gap shows that a few targeted assumptions, adding information on well-chosen parameters, can significantly improve forecast quality without requiring a very complex model.

> To go further, have a look at the [Streamlit app](https://legislatives2024.vicstorm.ovh) or at the code on [GitHub](https://github.com/victor-amblard/analyse-legislatives-2024), which I encourage you to explore: it lets you change many parameters (the preference ordering, for instance) and see how they affect the projection.
