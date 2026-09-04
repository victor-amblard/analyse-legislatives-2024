"""
Évaluation du modèle contre les résultats réels du 2nd tour 2024.

Mesure les deux propriétés qui définissent un bon modèle électoral :

1. **Couverture** (calibration) — le vrai résultat tombe-t-il dans l'intervalle
   prédit, à la fréquence annoncée ? Un intervalle à 90 % doit contenir la vraie
   valeur dans ~90 % des cas. Trop bas = modèle trop confiant ; trop haut =
   intervalles inutilement larges.
2. **Information** (finesse) — largeur moyenne de ces intervalles. Un modèle qui
   prédit « entre 0 et 100 % » a une couverture parfaite et ne sert à rien : les
   deux métriques ne se lisent qu'ensemble.

Le test est fait **par circonscription** (~500 observations) et pas seulement au
niveau national (7 partis) : c'est ce qui donne assez de points pour parler de
calibration plutôt que d'anecdote.

IMPORTANT — les résultats du 2nd tour ne servent qu'ici, en mesure. Dès qu'ils
alimentent la calibration du modèle, ces chiffres perdent leur sens : ils ne sont
honnêtes que parce que le modèle n'a jamais vu ces données.

Usage :
    python scripts/evaluate.py                       # 2000 tirages (~1 min)
    python scripts/evaluate.py --n-simus 500         # version rapide
    python scripts/evaluate.py --csv out.csv         # détail par circonscription
    python scripts/evaluate.py --model national      # variante de comparaison
"""

import argparse
import hashlib
from pathlib import Path

import numpy as np
import polars as pl

from analyse_legislatives import simulation
from analyse_legislatives.app_artifacts import write_app_artifact
from analyse_legislatives.data import (
    district_ids,
    load_full_results,
    load_second_round_results,
)
from analyse_legislatives.evaluation import (
    coverage_and_width,
    joint_region_scores,
    pit,
    probabilistic_and_median_scores,
)
from analyse_legislatives.config import DEFAULT_N_SIMUS, DEFAULT_SEED, MODEL_CONFIG_PATH
from analyse_legislatives.models import DEFAULT_MODEL, STOCHASTIC_MODELS, build
from analyse_legislatives.parties import (
    DESTINATION_LABELS,
    FAMILIES,
    SPECTRUM_LABELS,
)
from analyse_legislatives.utils.progress import progress_bar
from analyse_legislatives.projections import winners_by_simulation

NOMINAL_LEVELS = [0.50, 0.80, 0.90, 0.95]
FAMILY_LABELS = DESTINATION_LABELS[: len(FAMILIES)]


MIN_CALIBRATION_OBSERVATIONS = 100
"""En deçà, ni couverture ni PIT ne sont rapportées.

Avec 7 observations — les 7 familles — la couverture ne peut valoir que k/7.
Aucune de ces valeurs ne tombe à moins de 5 points de 50 %, 80 % ou 95 % : un
modèle PARFAITEMENT calibré était donc signalé « trop confiant » ou « trop
large » à ces trois niveaux avec probabilité 1. Les déciles PIT souffrent du
même défaut, chacun ne pouvant valoir que 0, 14 ou 29 %. Ces lignes mesuraient
la granularité de l'échantillon, pas le modèle."""


def coverage_flag(coverage: float, level: float, n: int) -> str:
    """Signale un écart qui dépasse le bruit d'échantillonnage binomial.

    Un seuil fixe à 5 points ne veut pas dire la même chose sur 7 et sur 1091
    observations. L'écart n'est annoté que s'il sort de l'intervalle à 95 % que
    produirait un modèle calibré sur ce nombre d'observations.

    AVERTISSEMENT : ces observations ne sont pas indépendantes — les parts d'une
    même circonscription sont liées par leur somme, et toutes partagent les
    tirages nationaux d'une simulation. L'effectif effectif est donc inférieur à
    `n` et cet intervalle est optimiste. Il sert à taire le bruit manifeste, pas
    à fonder un test.
    """
    margin = 1.96 * np.sqrt(level * (1 - level) / n)
    if abs(coverage - level) <= margin:
        return ""
    return "  (trop confiant)" if coverage < level else "  (trop large)"


def report_calibration(name: str, samples: np.ndarray, truth: np.ndarray, unit: str):
    n = truth.size
    print(f"\n  {name}  ({n} observations)")
    if n < MIN_CALIBRATION_OBSERVATIONS:
        print(
            f"    trop peu d'observations pour une calibration "
            f"(minimum {MIN_CALIBRATION_OBSERVATIONS})"
        )
        return
    print(f"    {'niveau':>8s} {'couverture':>12s} {'largeur moyenne':>18s}")
    for level in NOMINAL_LEVELS:
        cov, width = coverage_and_width(samples, truth, level)
        print(
            f"    {level:8.0%} {cov:12.1%} {width:14.2f} {unit}"
            f"{coverage_flag(cov, level, n)}"
        )
    values = pit(samples, truth)
    deciles = np.histogram(values, bins=10, range=(0, 1))[0] / values.size
    print(
        "    PIT par décile (10 % attendu partout) : "
        + " ".join(f"{v:.0%}" for v in deciles)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-simus", type=int, default=DEFAULT_N_SIMUS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--model",
        choices=list(STOCHASTIC_MODELS),
        default=DEFAULT_MODEL,
        help=(
            "'national' = modèle minimal, une seule matrice pour toutes les circos ; "
            "'national_anchored' = + part des suffrages exprimés ancrée ; "
            "'kernel_anchored' = + variations locales corrélées dans le département"
        ),
    )
    parser.add_argument("--csv", type=Path, help="écrit le détail par circonscription")
    parser.add_argument(
        "--seat-summary-csv",
        type=Path,
        help="écrit les quantiles nationaux de sièges utilisés par le billet",
    )
    parser.add_argument(
        "--joint-diagnostics-csv",
        type=Path,
        help="écrit les tirages et scores de la région prédictive jointe",
    )
    parser.add_argument(
        "--expressed-diagnostics-csv",
        type=Path,
        help="écrit la prédictive nationale et les erreurs médianes par circonscription",
    )
    parser.add_argument(
        "--app-artifact-dir",
        type=Path,
        help=(
            "écrit le cube et la matrice prédictive consommés par Streamlit ; "
            "réservé au modèle de déploiement"
        ),
    )
    args = parser.parse_args()

    first_round = load_full_results()
    actual = load_second_round_results()

    districts = [d for d in first_round.districts if d.circonscription.id in actual]
    missing = len(first_round.districts) - len(districts)
    if missing:
        print(
            f"AVERTISSEMENT : {missing} circonscriptions simulées sans résultat T2, ignorées."
        )

    print(
        f"{len(districts)} circonscriptions évaluées | N = {args.n_simus} tirages "
        f"| modèle = {args.model} (ordinal)"
    )
    model = build(args.model, seed=args.seed)
    with progress_bar(args.n_simus, "Simulation") as tick:
        cube = simulation.run(model, districts, args.n_simus, progress=tick)

    ids = [district.circonscription.id for district in districts]
    if args.app_artifact_dir:
        expected_ids = district_ids(first_round.districts)
        if ids != expected_ids:
            raise ValueError(
                "Impossible de produire l'artefact de l'app : l'évaluation ne "
                "couvre pas exactement les circonscriptions simulées."
            )
        with progress_bar(args.n_simus, "Matrice prédictive") as tick:
            prior_matrix = simulation.prior_predictive_median_matrix(
                build(args.model, seed=args.seed),
                districts,
                args.n_simus,
                progress=tick,
            )
        write_app_artifact(
            args.app_artifact_dir,
            cube=cube,
            prior_matrix=prior_matrix,
            model=args.model,
            seed=args.seed,
            config_sha256=hashlib.sha256(MODEL_CONFIG_PATH.read_bytes()).hexdigest(),
            district_ids=ids,
        )

    inscrits = np.array([first_round.inscrits_by_id[i] for i in ids], dtype=float)
    party_cube = cube[:, :, : len(FAMILIES)]
    exprimes_sim = party_cube.sum(axis=2)

    exprimes_true = np.array([actual[i].exprimes for i in ids], dtype=float)
    votes_true = np.array(
        [[actual[i].votes.get(f, 0) for f in FAMILY_LABELS] for i in ids], dtype=float
    )

    # ------------------------------------------------------------------ national
    print("\n" + "=" * 74)
    print("NIVEAU NATIONAL")
    print("=" * 74)

    winners_sim = winners_by_simulation(cube)
    seats_sim = np.stack(
        [(winners_sim == k).sum(axis=1) for k in range(len(FAMILIES))], axis=1
    ).astype(float)
    winners_true = votes_true.argmax(axis=1)
    seats_true = np.array(
        [(winners_true == k).sum() for k in range(len(FAMILIES))], dtype=float
    )
    for k, family in enumerate(FAMILY_LABELS):
        won_first_round = first_round.first_round_seats.get(family, 0)
        seats_sim[:, k] += won_first_round
        seats_true[k] += won_first_round

    order = [FAMILY_LABELS.index(p) for p in SPECTRUM_LABELS]
    print(
        f"\n  {'parti':>6s} {'réel':>6s} {'médiane':>9s} {'IC 90%':>15s} {'dans IC':>9s}"
    )
    for k in order:
        lo, hi = np.quantile(seats_sim[:, k], [0.05, 0.95])
        inside = lo <= seats_true[k] <= hi
        print(
            f"  {FAMILY_LABELS[k]:>6s} {seats_true[k]:6.0f} {np.median(seats_sim[:, k]):9.0f} "
            f"  [{lo:5.0f} — {hi:5.0f}] {'oui' if inside else 'NON':>9s}"
        )
    if args.seat_summary_csv:
        summary_rows = []
        for k in order:
            p05, p25, median, p75, p95 = np.quantile(
                seats_sim[:, k], [0.05, 0.25, 0.50, 0.75, 0.95]
            )
            summary_rows.append(
                {
                    "model": args.model,
                    "party": FAMILY_LABELS[k],
                    "actual": seats_true[k],
                    "p05": p05,
                    "p25": p25,
                    "median": median,
                    "p75": p75,
                    "p95": p95,
                }
            )
        args.seat_summary_csv.parent.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(summary_rows).write_csv(args.seat_summary_csv)

    # Pas de couverture ni de PIT sur les sièges : 7 familles ne suffisent pas
    # (voir MIN_CALIBRATION_OBSERVATIONS). Le tableau ci-dessus est ce qu'on peut
    # honnêtement dire par parti ; la calibration jointe est mesurée plus bas, sur
    # le vecteur entier, où elle a un sens.

    # ------------------------------------------------------------ energy score
    # Le vecteur de sièges est prédit *conjointement* : ses composantes sont liées
    # (elles somment au nombre de circonscriptions). L'energy score évalue cette
    # loi jointe contre l'unique vecteur observé.
    print("\n  Energy score du vecteur de sièges (unité : sièges)")
    es_nat, es_nat_det = probabilistic_and_median_scores(seats_sim, seats_true)
    print(
        f"    national                    : {es_nat:8.2f}   "
        f"(scénario médian seul : {es_nat_det:.2f})"
    )
    print("      → 1 seule observation : indicatif, non concluant.")

    calibration_scores, observed_score, percentile = joint_region_scores(
        seats_sim, seats_true
    )
    q50, q90 = np.quantile(calibration_scores, [0.50, 0.90], method="higher")
    print("\n  Région prédictive jointe du vecteur de sièges")
    print(
        f"    résultat réel : score {observed_score:.2f} | "
        f"percentile d'éloignement {percentile:.1%}"
    )
    print(
        f"    région 50 % : {'dedans' if observed_score <= q50 else 'HORS'} "
        f"(seuil {q50:.2f}) | région 90 % : "
        f"{'dedans' if observed_score <= q90 else 'HORS'} (seuil {q90:.2f})"
    )

    if args.joint_diagnostics_csv:
        roles = np.full(args.n_simus, "reference", dtype=object)
        roles[1::2] = "calibration"
        scores = np.full(args.n_simus, np.nan)
        scores[1::2] = calibration_scores
        diagnostics = (
            pl.DataFrame(seats_sim, schema=FAMILY_LABELS, orient="row")
            .with_columns(
                pl.lit(args.model).alias("model"),
                pl.Series("draw", np.arange(args.n_simus)),
                pl.Series("role", roles),
                pl.Series("joint_score", scores),
                pl.lit(float("nan")).alias("observed_percentile"),
            )
            .select(
                "model",
                "draw",
                "role",
                *FAMILY_LABELS,
                "joint_score",
                "observed_percentile",
            )
        )
        observed = {party: value for party, value in zip(FAMILY_LABELS, seats_true)}
        diagnostics = pl.concat(
            [
                diagnostics,
                pl.DataFrame(
                    [
                        {
                            "model": args.model,
                            "draw": -1,
                            "role": "observed",
                            **observed,
                            "joint_score": observed_score,
                            "observed_percentile": percentile,
                        }
                    ]
                ),
            ],
            how="vertical_relaxed",
        )
        args.joint_diagnostics_csv.parent.mkdir(parents=True, exist_ok=True)
        diagnostics.write_csv(args.joint_diagnostics_csv)

    nat_expressed_sim = exprimes_sim.sum(axis=1) / inscrits.sum() * 100
    nat_expressed_true = exprimes_true.sum() / inscrits.sum() * 100
    lo, hi = np.quantile(nat_expressed_sim, [0.05, 0.95])
    print(
        f"\n  Suffrages exprimés nationaux : réel {nat_expressed_true:.1f} % | "
        f"médiane {np.median(nat_expressed_sim):.1f} % | IC90 [{lo:.1f} — {hi:.1f}] "
        f"| {'dans IC' if lo <= nat_expressed_true <= hi else 'HORS IC'}"
    )

    # ------------------------------------------------- par circonscription
    print("\n" + "=" * 74)
    print("PAR CIRCONSCRIPTION")
    print("=" * 74)

    qualified = votes_true > 0
    share_sim = np.where(
        exprimes_sim[:, :, None] > 0,
        party_cube / np.maximum(exprimes_sim, 1)[:, :, None] * 100,
        0.0,
    )
    share_true = votes_true / exprimes_true[:, None] * 100

    d_idx, p_idx = np.nonzero(qualified)
    report_calibration(
        "Score des partis qualifiés (% exprimés)",
        share_sim[:, d_idx, p_idx],
        share_true[d_idx, p_idx],
        "pts",
    )

    expressed_sim = exprimes_sim / inscrits[None, :] * 100
    expressed_true = exprimes_true / inscrits * 100
    if args.expressed_diagnostics_csv:
        national = pl.DataFrame(
            {
                "model": args.model,
                "scope": "national_draw",
                "draw": np.arange(args.n_simus),
                "district_id": "",
                "predicted_share": nat_expressed_sim,
                "actual_share": nat_expressed_true,
            }
        )
        districts_summary = pl.DataFrame(
            {
                "model": args.model,
                "scope": "district",
                "draw": -1,
                "district_id": ids,
                "predicted_share": np.median(expressed_sim, axis=0),
                "actual_share": expressed_true,
            }
        )
        diagnostics = pl.concat([national, districts_summary], how="vertical_relaxed")
        diagnostics = diagnostics.with_columns(
            (pl.col("predicted_share") - pl.col("actual_share")).alias("error")
        )
        args.expressed_diagnostics_csv.parent.mkdir(parents=True, exist_ok=True)
        diagnostics.write_csv(args.expressed_diagnostics_csv)
    report_calibration(
        "Taux de suffrages exprimés (% inscrits)", expressed_sim, expressed_true, "pts"
    )

    win_prob = np.stack(
        [(winners_sim == k).mean(axis=0) for k in range(len(FAMILIES))], axis=1
    )
    predicted = win_prob.argmax(axis=1)
    accuracy = (predicted == winners_true).mean()
    prob_on_truth = win_prob[np.arange(len(districts)), winners_true]
    print(
        f"\n  Vainqueur : {accuracy:.1%} de circonscriptions correctes "
        f"({(predicted == winners_true).sum()}/{len(districts)})"
    )
    print(
        f"    probabilité moyenne attribuée au vrai vainqueur : {prob_on_truth.mean():.1%}"
    )
    # Restreinte aux partis RÉELLEMENT en lice. Sur les 7 x 501 = 3507 cellules du
    # tableau, 2416 concernent des partis absents du bulletin : leur probabilité de
    # victoire est nulle par construction, pas par jugement du modèle. Les inclure
    # remplissait la tranche 0-20 % de 2864 cas dont 84 % de zéros structurels, et
    # le « réalisé 0,8 % » qui en sortait ne mesurait rien.
    print("    calibration des probabilités de victoire (partis en lice) :")
    won = np.eye(len(FAMILIES))[winners_true].astype(bool)
    for lo_b, hi_b in [(0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]:
        sel = (win_prob >= lo_b) & (win_prob < hi_b) & qualified
        if sel.sum():
            realised = (won & sel).sum() / sel.sum()
            print(
                f"      prédit {lo_b:.0%}-{hi_b:.0%} : réalisé {realised:6.1%} ({sel.sum()} cas)"
            )

    if args.csv:
        rows = []
        for j, cid in enumerate(ids):
            for k, family in enumerate(FAMILY_LABELS):
                if not qualified[j, k]:
                    continue
                lo, hi = np.quantile(share_sim[:, j, k], [0.05, 0.95])
                rows.append(
                    {
                        "id_circo": cid,
                        "parti": family,
                        "score_reel": share_true[j, k],
                        "median_simule": np.median(share_sim[:, j, k]),
                        "p05": lo,
                        "p95": hi,
                        "dans_ic_90": lo <= share_true[j, k] <= hi,
                        "largeur_ic_90": hi - lo,
                        "proba_victoire": win_prob[j, k],
                        "vainqueur_reel": FAMILY_LABELS[winners_true[j]] == family,
                    }
                )
        pl.DataFrame(rows).write_csv(args.csv)
        print(f"\nDétail par circonscription écrit dans {args.csv}")


if __name__ == "__main__":
    main()
