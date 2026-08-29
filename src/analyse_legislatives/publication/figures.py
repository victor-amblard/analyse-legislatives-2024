"""Generate every static figure used by the blog."""

from analyse_legislatives.config import PROJECT_ROOT
from analyse_legislatives.publication.charts import write_classic_charts
from analyse_legislatives.publication.illustrations import (
    build_orderings_svg,
    build_prior_sankey_svg,
    build_simulation_animation_svg,
    build_simulation_pipeline_svg,
    build_turnout_flows_svg,
)

OUTPUT_DIR = PROJECT_ROOT / "site/public/figures"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    illustrations = {
        "preference-orderings.svg": build_orderings_svg,
        "prior-sankey.svg": build_prior_sankey_svg,
        "simulation-steps.svg": build_simulation_animation_svg,
        "simulation-pipeline.svg": build_simulation_pipeline_svg,
        "turnout-flows.svg": build_turnout_flows_svg,
    }
    for name, build in illustrations.items():
        path = OUTPUT_DIR / name
        path.write_text(build(), encoding="utf-8")
        print(f"wrote {path.relative_to(PROJECT_ROOT)}")
    write_classic_charts(OUTPUT_DIR)


if __name__ == "__main__":
    main()
