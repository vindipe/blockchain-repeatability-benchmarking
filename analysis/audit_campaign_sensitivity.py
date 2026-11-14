"""Summarize changes within configurations across dates and acquisition batches."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

try:
    from .audit_campaign_structure import CONFIG, DEFAULT_INPUT, DEFAULT_OUTPUT_DIR
    from .audit_observed_runs import load_runs
    from .derive_run_outcomes import derive_outcomes, prepare_selected_runs
except ImportError:  # Direct execution
    from audit_campaign_structure import CONFIG, DEFAULT_INPUT, DEFAULT_OUTPUT_DIR
    from audit_observed_runs import load_runs
    from derive_run_outcomes import derive_outcomes, prepare_selected_runs


METRICS = {
    "tps": ("average_throughput", "tps_point_valid_positive_commit"),
    "latency": ("average_latency", "latency_valid_positive_commit"),
    "energy": ("energy", "energy_valid_observed"),
}


def compare_periods(early: pd.DataFrame, late: pd.DataFrame) -> dict[str, float]:
    differences = {
        "positive_commit_pp": 100
        * (late["positive_commit_derived"].mean() - early["positive_commit_derived"].mean())
    }
    for metric, (value, eligible) in METRICS.items():
        before = early.loc[early[eligible], value].median()
        after = late.loc[late[eligible], value].median()
        differences[f"{metric}_pct"] = (
            100 * (after - before) / before if before > 0 else float("nan")
        )
    return differences


def run(input_path: Path, output_dir: Path) -> None:
    runs = derive_outcomes(prepare_selected_runs(load_runs(input_path))).sort_values(
        ["start_bench", "hash", "run"], kind="stable"
    )
    comparisons = {"late_vs_early_half": [], "last_vs_first_batch": []}
    for _, cell in runs.groupby(CONFIG, observed=True):
        half = len(cell) // 2
        if half:
            comparisons["late_vs_early_half"].append(
                compare_periods(cell.iloc[:half], cell.iloc[-half:])
            )

        # The input is sorted, so the first appearance of each hash orders the
        # batches by their earliest observed start time.
        batches = list(cell.groupby("hash", sort=False, observed=True))
        if len(batches) > 1:
            comparisons["last_vs_first_batch"].append(
                compare_periods(batches[0][1], batches[-1][1])
            )

    rows = []
    for comparison, estimates in comparisons.items():
        for metric, values in pd.DataFrame(estimates).items():
            rows.append(
                {
                    "comparison": comparison,
                    "metric": metric,
                    "eligible_configurations": int(values.count()),
                    "q25": values.quantile(0.25),
                    "median": values.median(),
                    "q75": values.quantile(0.75),
                }
            )
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(
        output_dir / "campaign_sensitivity.csv", index=False, float_format="%.6f"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    run(args.input, args.output_dir)
