"""Reproduit les résultats publiables et, sur demande, les figures du write-up.

La configuration scientifique (modèle par défaut, seed, nombre de simulations,
priors et ordres) vient exclusivement de ``config/model.yaml``. Chaque sortie
texte est accompagnée d'un manifeste JSON contenant cette configuration et son
empreinte SHA-256.

Usage :
    python scripts/reproduce.py
    python scripts/reproduce.py --figures
    python scripts/reproduce.py --figures --kernel-sensitivity
    python scripts/reproduce.py --models national national_anchored --n-simus 200
"""

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from analyse_legislatives.config import (
    DEFAULT_N_SIMUS,
    DEFAULT_SEED,
    MODEL_CONFIG,
    MODEL_CONFIG_PATH,
)
from analyse_legislatives.models import PUBLICATION_MODELS
from analyse_legislatives.config import PROJECT_ROOT

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts/publication/models"


def display_path(path: Path) -> Path:
    """Chemin relatif au projet si possible, absolu pour une sortie externe."""
    try:
        return path.relative_to(PROJECT_ROOT)
    except ValueError:
        return path


def announce(index: int, total: int, label: str) -> None:
    """Annonce l'étape en cours sur stderr, où l'étape elle-même dessinera sa
    barre juste en dessous."""
    print(f"[{index}/{total}] {label}", file=sys.stderr, flush=True)


def capture(command: Sequence[str]) -> str:
    """Exécute une étape dont la SORTIE est un résultat à conserver.

    Seul stdout est capturé : le stderr de l'enfant reste branché sur le
    terminal, ce qui laisse passer sa barre de progression en direct et affiche
    sa trace d'erreur telle quelle si l'étape échoue.
    """
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return completed.stdout


def stream(command: Sequence[str]) -> None:
    """Exécute une étape dont la sortie n'est qu'un compte rendu à lire.

    Rien n'est capturé : les lignes s'affichent au fil de l'eau au lieu
    d'apparaître d'un bloc à la fin, ce qui est la seule progression visible des
    étapes qui n'ont pas de barre (la génération des figures)."""
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--figures", action="store_true", help="régénère aussi les SVG")
    parser.add_argument(
        "--kernel-sensitivity",
        action="store_true",
        help="recalcule la grille coûteuse (h, lambda) avant de générer les figures",
    )
    parser.add_argument("--alpha-sensitivity", action="store_true")
    parser.add_argument(
        "--models", nargs="+", choices=PUBLICATION_MODELS, default=PUBLICATION_MODELS
    )
    parser.add_argument("--n-simus", type=int, default=DEFAULT_N_SIMUS)
    parser.add_argument(
        "--prior-simus",
        type=int,
        default=3000,
        help="tirages par alpha pour les figures de sensibilité",
    )
    parser.add_argument(
        "--kernel-sensitivity-simus",
        type=int,
        default=300,
        help="tirages par cellule pour la sensibilité croisée (h, lambda)",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    if args.kernel_sensitivity and not args.figures:
        parser.error("--kernel-sensitivity requiert --figures")

    figure_models = {"national_anchored", "kernel_anchored"}
    if args.figures and not figure_models.issubset(args.models):
        parser.error(
            "--figures requiert national_anchored et kernel_anchored pour "
            "reconstruire la comparaison des intervalles de sièges"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    steps = [f"évaluation {model}" for model in args.models]
    if args.figures:
        if args.alpha_sensitivity:
            steps.append("sensibilité à alpha")
        if args.kernel_sensitivity:
            steps.append("sensibilité au noyau (h, lambda)")
        steps.append("exemple de simulation 0101")
        steps.append("figures")
    done = 0

    for model in args.models:
        done += 1
        announce(done, len(steps), f"évaluation {model} ({args.n_simus} tirages)")
        output = capture(
            [
                sys.executable,
                "scripts/evaluate.py",
                "--model",
                model,
                "--n-simus",
                str(args.n_simus),
                "--seed",
                str(DEFAULT_SEED),
                "--seat-summary-csv",
                str(args.output_dir / f"seat-intervals-{model}.csv"),
                "--joint-diagnostics-csv",
                str(args.output_dir / f"joint-diagnostics-{model}.csv"),
                "--expressed-diagnostics-csv",
                str(args.output_dir / f"expressed-diagnostics-{model}.csv"),
            ]
        )
        path = args.output_dir / f"evaluation-{model}.txt"
        path.write_text(output, encoding="utf-8")
        print(f"wrote {display_path(path)}", flush=True)

    if args.figures:
        if args.alpha_sensitivity:
            done += 1
            announce(done, len(steps), "sensibilité à alpha")
            stream(
                [
                    sys.executable,
                    "scripts/analyses/alpha_sensitivity.py",
                    "--n-simus",
                    str(args.prior_simus),
                ]
            )
        if args.kernel_sensitivity:
            done += 1
            announce(done, len(steps), "sensibilité au noyau (h, lambda)")
            stream(
                [
                    sys.executable,
                    "scripts/analyses/kernel_sensitivity.py",
                    "--n-simus",
                    str(args.kernel_sensitivity_simus),
                ]
            )
        done += 1
        announce(done, len(steps), "exemple de simulation 0101")
        stream(
            [
                sys.executable,
                "scripts/analyses/simulation_example.py",
                "--n-simus",
                str(args.n_simus),
                "--seed",
                str(DEFAULT_SEED),
            ]
        )
        done += 1
        announce(done, len(steps), "figures")
        stream([sys.executable, "-m", "analyse_legislatives.publication.figures"])

    raw_config = MODEL_CONFIG_PATH.read_bytes()
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "seed": DEFAULT_SEED,
        "n_simulations": args.n_simus,
        "models": list(args.models),
        "figures": args.figures,
        "kernel_sensitivity_recomputed": args.kernel_sensitivity,
        "prior_simulations_per_alpha": args.prior_simus if args.figures else None,
        "kernel_sensitivity_simulations_per_cell": (
            args.kernel_sensitivity_simus if args.kernel_sensitivity else None
        ),
        "config_sha256": hashlib.sha256(raw_config).hexdigest(),
        "config": MODEL_CONFIG.model_dump(mode="json"),
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {display_path(manifest_path)}")


if __name__ == "__main__":
    main()
