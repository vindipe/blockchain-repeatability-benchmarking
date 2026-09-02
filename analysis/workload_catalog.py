"""Generate the six-workload catalog and observed outcome counts for R1.1/R1.13."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

try:
    from .audit_observed_runs import DEFAULT_INPUT, load_runs
    from .derive_run_outcomes import derive_outcomes, prepare_selected_runs
except ImportError:  # Direct execution
    from audit_observed_runs import DEFAULT_INPUT, load_runs  # type: ignore[no-redef]
    from derive_run_outcomes import (  # type: ignore[no-redef]
        derive_outcomes,
        prepare_selected_runs,
    )


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "m1_workloads"
DEFAULT_TABLE = (
    REPOSITORY_ROOT
    / "paper_tables"
    / "six_workloads"
    / "table_workload_catalog.tex"
)

WORKLOADS = {
    "DDoS": {
        "raw_label": "10000",
        "transaction_profile": "Simple transfer",
        "offered_load": "10,000 TPS (constant)",
        "demand_regime": "Very-high steady rate",
        "source": "Diablo-v2",
    },
    "FIFA": {
        "raw_label": "football",
        "transaction_profile": "FIFA smart contract",
        "offered_load": "FIFA-derived trace",
        "demand_regime": "Contention-oriented",
        "source": "Diablo-v2",
    },
    "GAFAM": {
        "raw_label": "gafam",
        "transaction_profile": "Stock-trading smart contract",
        "offered_load": "19,800 TPS at 0 s; 25--140 TPS after 1 s",
        "demand_regime": "Bursty",
        "source": "Diablo-v2; Nasdaq",
    },
    "Gaming": {
        "raw_label": "dota",
        "transaction_profile": "Dota 2 smart contract",
        "offered_load": "Dota-2-derived trace",
        "demand_regime": "High sending rate",
        "source": "Diablo-v2",
    },
    "PayPal": {
        "raw_label": "paypal",
        "transaction_profile": "Simple transfer",
        "offered_load": "200 TPS (constant)",
        "demand_regime": "Moderate steady rate",
        "source": "paymentSystems",
    },
    "VISA": {
        "raw_label": "visa",
        "transaction_profile": "Simple transfer",
        "offered_load": "1,800 TPS (constant)",
        "demand_regime": "High steady rate",
        "source": "Diablo-v2",
    },
}


def build_catalog(derived: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for workload, definition in WORKLOADS.items():
        subset = derived.loc[derived["workload"] == workload]
        cells = subset.groupby(
            ["blockchain", "mode", "workload", "network_size"], observed=True
        ).size()
        rows.append(
            {
                "workload": workload,
                **definition,
                "configuration_cells": int(len(cells)),
                "observed_executions": int(len(subset)),
                "positive_commit": int(subset["positive_commit_derived"].sum()),
                "zero_commit": int(subset["zero_commit_derived"].sum()),
                "no_submission": int(subset["no_submission_derived"].sum()),
                "minimum_observed_per_cell": int(cells.min()),
                "maximum_observed_per_cell": int(cells.max()),
            }
        )
    return pd.DataFrame(rows)


def render_table(catalog: pd.DataFrame) -> str:
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{\vd{R1.1-2-12-13: Six workload profiles and observed outcome accounting. Offered loads and trace characteristics follow the released Lilith/Diablo inputs; counts refer to the selected repeated-execution corpus.}}",
        r"\label{tab:six_workload_catalog}",
        r"\TableFont",
        r"\setlength{\tabcolsep}{2pt}",
        r"\begin{tabular}{llllrrrr}",
        r"\hline",
        "Workload & Raw label & Transaction profile & Offered-load pattern & "
        "Cells & Observed & Positive & Zero commit \\\\",
        r"\hline",
    ]
    for _, row in catalog.iterrows():
        lines.append(
            f"{row['workload']} & {row['raw_label']} & {row['transaction_profile']} & "
            f"{row['offered_load']} & {row['configuration_cells']} & "
            f"{row['observed_executions']} & {row['positive_commit']} & "
            f"{row['zero_commit']} \\\\"
        )
    lines.extend(
        [
            r"\hline",
            r"\end{tabular}",
            r"\vspace{1mm}",
            r"\parbox{\textwidth}{\TableFont The raw labels \texttt{10000}, \texttt{football}, \texttt{gafam}, and \texttt{dota} are reported as DDoS, FIFA, GAFAM, and Gaming, respectively. The GAFAM trace contains a 19,800-TPS control point at 0~s, falls to 115~TPS at 1~s, uses 25--140-TPS control points through 180~s, and reaches zero at 300~s; Diablo linearly interpolates between control points. Gaming also contains the corpus's two no-submission observations. DDoS denotes the artifact's 10,000-TPS workload label; the present study does not infer that an observed zero-commit execution was caused by a network attack.}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def run(input_path: Path, output_dir: Path, table_path: Path) -> dict[str, object]:
    derived = derive_outcomes(prepare_selected_runs(load_runs(input_path)))
    catalog = build_catalog(derived)
    output_dir.mkdir(parents=True, exist_ok=True)
    table_path.parent.mkdir(parents=True, exist_ok=True)
    catalog.to_csv(output_dir / "workload_catalog.csv", index=False)
    table_path.write_text(render_table(catalog), encoding="utf-8")
    summary = {
        "workloads": int(len(catalog)),
        "configuration_cells": int(catalog["configuration_cells"].sum()),
        "observed_executions": int(catalog["observed_executions"].sum()),
        "positive_commit": int(catalog["positive_commit"].sum()),
        "zero_commit": int(catalog["zero_commit"].sum()),
        "no_submission": int(catalog["no_submission"].sum()),
        "minimum_observed_per_cell": int(catalog["minimum_observed_per_cell"].min()),
        "maximum_observed_per_cell": int(catalog["maximum_observed_per_cell"].max()),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(json.dumps(run(args.input, args.output_dir, args.table), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
