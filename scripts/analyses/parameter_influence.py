"""
Croyance injectée ≠ influence sur le résultat.

`prior_information_chart` mesure la première : combien chaque prior s'écarte de
l'uniforme, en bits. Elle ne dit rien de la seconde. Un prior très affirmé peut
ne rien changer aux sièges — auquel cas l'hypothèse est forte mais inoffensive ;
un prior presque plat peut au contraire piloter le résultat.

Ce script mesure l'influence sur la même prédictive a priori que le billet. Son
résultat principal compare les dix déciles de chaque paramètre :

  - le déplacement de la médiane du nombre de sièges ;
  - la variation de la largeur de l'intervalle prédictif à 90 %.

Il conserve aussi, comme diagnostic complémentaire, la part de la VARIANCE du
nombre de sièges que chaque paramètre explique à lui seul,

    eta^2 = Var(E[sièges | paramètre]) / Var(sièges)

estimée par tranches à effectif égal (indice de sensibilité du premier ordre,
au sens de l'analyse de sensibilité globale). Estimé « sur données » plutôt que
par un plan d'échantillonnage dédié (Saltelli), donc bruité : deux garde-fous
plutôt qu'une confiance aveugle dans le classement obtenu —

  - un PLANCHER DE BRUIT par permutation : on recalcule eta^2 contre un
    paramètre purement aléatoire, indépendant des sièges par construction. Tout
    ce qui passe sous ce plancher est indiscernable de zéro ;
  - deux GRAINES, pour vérifier qu'un écart mesuré n'est pas un artefact de
    tirage.

Les amplitudes sont des étendues sur les dix déciles : elles mesurent la force
de l'effet sans dépendre du sens choisi pour paramétrer la variable. Les
planchers par permutation donnent l'amplitude que le seul bruit Monte-Carlo
peut produire.

Les indices du premier ordre ne captent pas les interactions et somment à moins
de 1 : le reste revient aux ordres de préférence (dont les ex æquo sont retirés
à chaque simulation), au bruit multinomial et aux interactions.

IMPORTANT — aucun résultat du 2nd tour n'entre ici : tout est a priori.

Usage :
    python scripts/analyses/parameter_influence.py
    python scripts/analyses/parameter_influence.py --n-simus 4000 --parties NFP+ ENS+ RN+
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl

from analyse_legislatives.config import DEFAULT_N_SIMUS, DEFAULT_SEED, PROJECT_ROOT
from analyse_legislatives.data import load_full_results
from analyse_legislatives.models import build
from analyse_legislatives.parties import DESTINATIONS, FAMILIES
from analyse_legislatives.projections import winners_by_simulation
from analyse_legislatives.utils.progress import progress_bar

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "publication" / "sensitivity"
DEFAULT_MODEL = "kernel_anchored"
DEFAULT_PARTIES = ("RN+",)
DEFAULT_DISTRICT = "0101"
"""La circonscription dont on suit l'écart local, la même que celle du billet."""

N_BINS = 10
N_ETA_PERMUTATIONS = 200
N_SWING_PERMUTATIONS = 1_000
FAMILY_LABELS = [str(family) for family in FAMILIES]

# Noms alignés sur les panneaux de `prior_information_chart` : les deux figures
# parlent des mêmes objets, et le graphique final les apparie par ce libellé.
PARAMETER_LABELS = {
    "alpha": "Concentration α",
    "qualified_demobilisation": "Démobilisation d",
    "non_expressed_retention": "Rétention des non-exprimés",
    "tilt": "Tilt τ",
    "delta_nat": "Dérive nationale δnat",
    "delta_district": "Écart local δ0101",
    "mixing_weight": "Mélange national λ",
    "department_correlation": "Corrélation département ρd",
    "region_correlation": "Corrélation région ρr",
}


def eta_squared(x: np.ndarray, y: np.ndarray, n_bins: int = N_BINS) -> float:
    """Part de la variance de `y` expliquée par `x` seul.

    Tranches à effectif égal plutôt qu'à largeur égale, comme dans
    `win_probability_calibration.py` et pour la même raison : les paramètres ont
    des lois très asymétriques (Beta(2,38) tient presque entièrement sous 0,1),
    et des tranches à largeur fixe y seraient vides ou dégénérées.

    Un paramètre CONSTANT (imposé plutôt que tiré) n'explique rien : eta^2 = 0,
    et non une division par zéro.
    """
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return 0.0
    order = np.argsort(x, kind="stable")
    ys = y[order]
    grand = ys.mean()
    total = float(((ys - grand) ** 2).sum())
    between = sum(
        len(chunk) * (chunk.mean() - grand) ** 2
        for chunk in np.array_split(ys, n_bins)
        if len(chunk)
    )
    return float(between / total)


def noise_floor(y: np.ndarray, rng: np.random.Generator, n_bins: int = N_BINS) -> float:
    """Niveau d'`eta^2` atteint par un paramètre SANS aucun lien avec `y`.

    Découper en `n_bins` tranches puis comparer leurs moyennes capte toujours un
    peu de bruit : l'espérance de `eta^2` sous l'hypothèse nulle vaut environ
    `(n_bins - 1) / n`, pas zéro. On la mesure ici plutôt que de l'approcher, en
    rejouant l'estimation contre un tirage indépendant, et on retient le 95e
    centile : au-dessus, l'influence n'est plus explicable par le seul découpage.
    """
    draws = [
        eta_squared(rng.random(len(y)), y, n_bins) for _ in range(N_ETA_PERMUTATIONS)
    ]
    return float(np.quantile(draws, 0.95))


def conditional_quantiles(
    x: np.ndarray, y: np.ndarray, n_bins: int = N_BINS
) -> list[dict[str, float]]:
    """Intervalle de `y` dans chaque tranche à effectif égal de `x`.

    C'est la lecture qui intéresse vraiment ici : `eta^2` ne suit que la MOYENNE
    conditionnelle, alors qu'un paramètre peut très bien laisser la médiane en
    place et n'écarter que les bornes — c'est précisément ce qu'on attend d'un
    paramètre de dispersion comme alpha. Suivre p05, p50 et p95 séparément le
    rend visible ; une statistique unique le masquerait.
    """
    order = np.argsort(x, kind="stable")
    ys = y[order]
    rows = []
    for decile, chunk in enumerate(np.array_split(ys, n_bins)):
        rows.append(
            {
                "decile": decile,
                "p05": float(np.quantile(chunk, 0.05)),
                "p50": float(np.quantile(chunk, 0.50)),
                "p95": float(np.quantile(chunk, 0.95)),
            }
        )
    return rows


def joint_swing_noise_floor(
    outcomes: list[np.ndarray],
    rng: np.random.Generator,
    n_bins: int = N_BINS,
) -> dict[str, float]:
    """Bruit des amplitudes après moyenne des profils de plusieurs graines.

    La statistique publiée moyenne les quantiles conditionnels entre les graines
    avant de prendre leur étendue sur dix déciles. Le plancher reproduit
    exactement cette procédure sur des permutations indépendantes des sièges.
    """
    floors: dict[str, list[float]] = {"p05": [], "p50": [], "p95": [], "largeur": []}
    for _ in range(N_SWING_PERMUTATIONS):
        profiles = []
        for y in outcomes:
            shuffled = y[np.argsort(rng.random(len(y)), kind="stable")]
            profiles.append(
                np.array(
                    [
                        [np.quantile(chunk, p) for p in (0.05, 0.50, 0.95)]
                        for chunk in np.array_split(shuffled, n_bins)
                    ]
                )
            )
        quantiles = np.mean(profiles, axis=0)
        spread = lambda values: float(np.ptp(values))  # noqa: E731
        floors["p05"].append(spread(quantiles[:, 0]))
        floors["p50"].append(spread(quantiles[:, 1]))
        floors["p95"].append(spread(quantiles[:, 2]))
        floors["largeur"].append(spread(quantiles[:, 2] - quantiles[:, 0]))
    return {k: float(np.quantile(v, 0.95)) for k, v in floors.items()}


def traced_run(model, districts, n_simus: int, district_index: int, progress):
    """`simulation.run`, mais en gardant les paramètres de chaque tirage.

    Les étapes sont celles de `Model.predict_all_circonscriptions`, dans le même
    ordre : à graine égale, la séquence d'appels au générateur est identique et
    le cube produit ici est celui qu'aurait produit `simulation.run`. C'est
    vérifié par `--check-run`.
    """
    cube = np.zeros((n_simus, len(districts), len(DESTINATIONS)), dtype=np.int64)
    traces: list[dict[str, float]] = []

    for i_simu in range(n_simus):
        draw = model.draw_simulation()
        matrices = model.sample_transfer_matrices(districts, draw)
        tilts = model.tilts_for_districts(districts, draw)

        # Lu APRÈS `sample_transfer_matrices` : c'est elle qui déclenche
        # `_begin_simulation` (les deux rho) puis `_complete_matrices` (les
        # deltas). Les accesseurs renvoient la valeur mise en cache pour la
        # simulation en cours, ils ne retirent pas.
        rho_dept = model.department_correlation_for()
        trace = {
            "alpha": draw.alpha,
            "qualified_demobilisation": draw.qualified_demobilisation,
            "non_expressed_retention": draw.non_expressed_retention,
            "tilt": draw.tilt,
            "mixing_weight": draw.mixing_weight,
            "department_correlation": rho_dept,
            "region_correlation": model.region_correlation_for(rho_dept),
            "delta_nat": model._drawn_national_change,
            "delta_district": float(model._drawn_local_changes[district_index]),
        }
        traces.append(trace)

        for i_district, district in enumerate(districts):
            prediction = model.predict_circonscription(
                district, matrices[i_district], float(tilts[i_district])
            )
            for i_dest, destination in enumerate(DESTINATIONS):
                cube[i_simu, i_district, i_dest] = prediction.results[destination]

        if progress is not None:
            progress(i_simu + 1, n_simus)

    return cube, pl.DataFrame(traces)


def seats_by_simulation(cube: np.ndarray, first_round_seats) -> np.ndarray:
    """Sièges par parti et par simulation, premier tour inclus."""
    winners = winners_by_simulation(cube)
    seats = np.stack(
        [(winners == k).sum(axis=1) for k in range(len(FAMILIES))], axis=1
    ).astype(float)
    for k, family in enumerate(FAMILY_LABELS):
        seats[:, k] += first_round_seats.get(family, 0)
    return seats


def influence_for_seed(model_name, districts, n_simus, seed, district_index):
    model = build(model_name, seed=seed)
    with progress_bar(n_simus, f"{model_name} (graine {seed})") as tick:
        return traced_run(model, districts, n_simus, district_index, tick)


def seat_column(party: str) -> str:
    """Nom stable de la colonne parquet contenant les sièges d'un parti."""
    return f"sieges_{party.lower().replace('+', '_plus').replace(' ', '_')}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=DEFAULT_N_SIMUS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--seed-check", type=int, default=DEFAULT_SEED + 1)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--parties", nargs="+", default=list(DEFAULT_PARTIES))
    parser.add_argument("--district", default=DEFAULT_DISTRICT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=None,
        help="dossier où déposer les tirages bruts (paramètres + sièges) en parquet",
    )
    parser.add_argument(
        "--from-raw",
        type=Path,
        default=None,
        help="recalculer les statistiques depuis des tirages déjà enregistrés,"
        " sans relancer la simulation",
    )
    parser.add_argument(
        "--check-run",
        action="store_true",
        help="vérifie que la boucle tracée reproduit `simulation.run` à graine égale",
    )
    args = parser.parse_args()

    first_round = load_full_results()
    districts = first_round.districts
    ids = [d.circonscription.id for d in districts]
    if args.district not in ids:
        raise SystemExit(f"circonscription inconnue : {args.district}")
    district_index = ids.index(args.district)
    unknown_parties = sorted(set(args.parties) - set(FAMILY_LABELS))
    if unknown_parties:
        raise SystemExit(
            f"familles politiques inconnues : {', '.join(unknown_parties)}"
        )

    if args.check_run:
        from analyse_legislatives import simulation

        reference = simulation.run(
            build(args.model, seed=args.seed), districts, 12, progress=None
        )
        traced, _ = traced_run(
            build(args.model, seed=args.seed), districts, 12, district_index, None
        )
        assert np.array_equal(reference, traced), (
            "la boucle tracée a divergé de simulation.run"
        )
        print("boucle tracée identique à simulation.run\n")

    rows = []
    profile_rows = []
    outcomes: dict[str, list[np.ndarray]] = {party: [] for party in args.parties}
    seeds = (args.seed, args.seed_check)
    for seed in seeds:
        if args.from_raw is not None:
            raw = pl.read_parquet(args.from_raw / f"draws-{args.model}-{seed}.parquet")
            missing = [
                seat_column(party)
                for party in args.parties
                if seat_column(party) not in raw.columns
            ]
            if missing:
                raise SystemExit(
                    "tirages bruts incomplets : colonnes absentes "
                    f"{', '.join(missing)}. Relancez sans --from-raw et avec --raw-dir."
                )
            traces = raw.select(*PARAMETER_LABELS)
            seats_for_party = {
                party: raw[seat_column(party)].to_numpy() for party in args.parties
            }
            args.n_simus = len(raw)
        else:
            cube, traces = influence_for_seed(
                args.model, districts, args.n_simus, seed, district_index
            )
            seats = seats_by_simulation(cube, first_round.first_round_seats)
            seats_for_party = {
                party: seats[:, FAMILY_LABELS.index(party)] for party in args.parties
            }

            if args.raw_dir is not None:
                args.raw_dir.mkdir(parents=True, exist_ok=True)
                traces.with_columns(
                    pl.Series(seat_column(party), values)
                    for party, values in seats_for_party.items()
                ).write_parquet(
                    args.raw_dir / f"draws-{args.model}-{seed}.parquet",
                )

        for party, y in seats_for_party.items():
            outcomes[party].append(y)
            floor = noise_floor(y, np.random.default_rng(seed))
            profile_rows.append(
                {
                    "graine": seed,
                    "parti": party,
                    "parametre": "toutes",
                    "colonne": "toutes",
                    "decile": -1,
                    "p05": float(np.quantile(y, 0.05)),
                    "p50": float(np.quantile(y, 0.50)),
                    "p95": float(np.quantile(y, 0.95)),
                }
            )
            for column, label in PARAMETER_LABELS.items():
                x = traces[column].to_numpy()
                rows.append(
                    {
                        "graine": seed,
                        "parti": party,
                        "parametre": label,
                        "colonne": column,
                        "eta2": eta_squared(x, y),
                        "plancher_bruit": floor,
                    }
                )
                for entry in conditional_quantiles(x, y):
                    profile_rows.append(
                        {
                            "graine": seed,
                            "parti": party,
                            "parametre": label,
                            "colonne": column,
                            **entry,
                        }
                    )

    swing_floors = pl.DataFrame(
        [
            {
                "parti": party,
                **joint_swing_noise_floor(
                    party_outcomes,
                    np.random.default_rng(args.seed + 10_000 + party_index),
                ),
            }
            for party_index, (party, party_outcomes) in enumerate(outcomes.items())
        ]
    ).rename({"p50": "plancher_p50", "largeur": "plancher_largeur"})

    table = pl.DataFrame(rows)
    summary = (
        table.group_by("parti", "parametre", "colonne")
        .agg(
            pl.col("eta2").mean().alias("part_variance"),
            pl.col("eta2").min().alias("part_variance_min"),
            pl.col("eta2").max().alias("part_variance_max"),
            pl.col("plancher_bruit").max().alias("plancher_bruit"),
        )
        .with_columns(
            (pl.col("part_variance") > pl.col("plancher_bruit")).alias(
                "au_dessus_bruit"
            )
        )
        .sort("parti", "part_variance", descending=[False, True])
    )

    # Profil moyenné sur les graines : un intervalle par décile de chaque
    # paramètre, plus la référence non conditionnée au décile -1.
    profile = (
        pl.DataFrame(profile_rows)
        .group_by("parti", "parametre", "colonne", "decile")
        .agg(
            pl.col("p05").mean(),
            pl.col("p50").mean(),
            pl.col("p95").mean(),
        )
        .sort("parti", "parametre", "decile")
    )
    swings = (
        profile.filter(pl.col("decile") >= 0)
        .group_by("parti", "parametre", "colonne")
        .agg(
            (pl.col("p05").max() - pl.col("p05").min()).alias("amplitude_p05"),
            (pl.col("p50").max() - pl.col("p50").min()).alias("amplitude_p50"),
            (pl.col("p95").max() - pl.col("p95").min()).alias("amplitude_p95"),
            (
                (pl.col("p95") - pl.col("p05")).max()
                - (pl.col("p95") - pl.col("p05")).min()
            ).alias("amplitude_largeur"),
        )
        .join(
            swing_floors.select("parti", "plancher_p50", "plancher_largeur"), on="parti"
        )
        .with_columns(
            pl.max_horizontal("amplitude_p05", "amplitude_p50", "amplitude_p95").alias(
                "amplitude_max"
            ),
        )
        .with_columns(
            (pl.col("amplitude_p50") > pl.col("plancher_p50")).alias("decale_vraiment"),
            (pl.col("amplitude_largeur") > pl.col("plancher_largeur")).alias(
                "elargit_vraiment"
            ),
        )
        .sort("parti", "amplitude_max", descending=[False, True])
    )
    summary = summary.join(
        swings.select(
            "parti",
            "parametre",
            "colonne",
            "amplitude_p50",
            "amplitude_largeur",
            "plancher_p50",
            "plancher_largeur",
            "decale_vraiment",
            "elargit_vraiment",
        ),
        on=["parti", "parametre", "colonne"],
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f"parameter-influence-{args.model}.csv"
    summary.write_csv(path)
    profile_path = args.output_dir / f"parameter-interval-profile-{args.model}.csv"
    profile.write_csv(profile_path)
    swings_path = args.output_dir / f"parameter-interval-swing-{args.model}.csv"
    swings.write_csv(swings_path)

    for party in args.parties:
        party_profile = profile.filter(pl.col("parti") == party)
        full_interval = party_profile.filter(pl.col("decile") == -1)
        party_swings = swings.filter(pl.col("parti") == party)
        party_summary = summary.filter(pl.col("parti") == party)
        print(
            f"\nIntervalle à 90 % des sièges {party}, toutes simulations : "
            f"[{full_interval['p05'][0]:.0f} — {full_interval['p95'][0]:.0f}]"
            f" (médiane {full_interval['p50'][0]:.0f})\n"
        )
        print(
            f"  {'paramètre':28s} {'Δp50':>7s} {'décale':>7s}"
            f" {'Δlargeur':>9s} {'élargit':>8s}"
        )
        for row in party_swings.iter_rows(named=True):
            print(
                f"  {row['parametre']:28s} {row['amplitude_p50']:7.1f}"
                f" {'oui' if row['decale_vraiment'] else 'non':>7s}"
                f" {row['amplitude_largeur']:9.1f}"
                f" {'oui' if row['elargit_vraiment'] else 'non':>8s}"
            )
        print(
            "\n  planchers appariés (95e centile) : "
            f"{party_swings['plancher_p50'][0]:.1f} sur la médiane, "
            f"{party_swings['plancher_largeur'][0]:.1f} sur la largeur"
        )
        print(
            f"  somme des indices du 1er ordre : "
            f"{party_summary['part_variance'].sum():.1%}"
        )

    print(
        f"\nModèle {args.model}, {args.n_simus} simulations, "
        f"graines {args.seed} et {args.seed_check}"
    )
    for written in (path, profile_path, swings_path):
        print(f"wrote {written}")


if __name__ == "__main__":
    main()
