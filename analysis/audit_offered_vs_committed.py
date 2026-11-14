"""Summarize matched offered and committed load from the released run records."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

try:
    from .audit_observed_runs import DEFAULT_INPUT, load_runs
    from .derive_run_outcomes import derive_outcomes, prepare_selected_runs
except ImportError:  # Direct execution
    from audit_observed_runs import DEFAULT_INPUT, load_runs
    from derive_run_outcomes import derive_outcomes, prepare_selected_runs


DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[1] / "outputs" / "revision" / "r3_9_offered_load"
)


def summarize(runs: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    submitted = runs["submitted_derived"]
    paired_runs = runs.assign(
        offered_tps=runs["average_load"].where(submitted),
        committed_tps=runs["average_throughput"].where(submitted),
        committed_pct=100 * runs["commit_number"].div(runs["submit_number"].where(submitted)),
    )
    return (
        paired_runs.groupby(keys, observed=True)
        .agg(
            observed_runs=("run", "size"),
            submitted_runs=("submitted_derived", "sum"),
            zero_commit_runs=("zero_commit_derived", "sum"),
            no_submission_runs=("no_submission_derived", "sum"),
            censored_positive_tps_runs=("tps_censored_positive_commit", "sum"),
            median_offered_tps=("offered_tps", "median"),
            median_exported_committed_tps=("committed_tps", "median"),
            median_per_run_committed_pct=("committed_pct", "median"),
        )
        .reset_index()
    )


def run(input_path: Path, output_dir: Path) -> None:
    runs = derive_outcomes(prepare_selected_runs(load_runs(input_path)))
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, keys in (
        ("by_workload", ["workload"]),
        ("by_workload_blockchain_size", ["workload", "blockchain", "network_size"]),
    ):
        summarize(runs, keys).to_csv(
            output_dir / f"{name}.csv", index=False, float_format="%.6f"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    run(args.input, args.output_dir)
