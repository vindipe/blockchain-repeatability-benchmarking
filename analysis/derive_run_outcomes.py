"""Derive observable run outcomes and metric-specific eligibility masks.

The rules in this module use only fields present in the released CSV.  They do
not infer deployment or execution failures for which no supporting logs exist.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from .audit_observed_runs import (
        CONFIGURATION_COLUMNS,
        DEFAULT_INPUT,
        PRIMARY_WORKLOADS_LEGACY,
        load_runs,
        normalise_labels,
        select_controlled_corpus,
        sha256_file,
        validate_provenance,
    )
except ImportError:  # Direct execution: python3 analysis/derive_run_outcomes.py
    from audit_observed_runs import (  # type: ignore[no-redef]
        CONFIGURATION_COLUMNS,
        DEFAULT_INPUT,
        PRIMARY_WORKLOADS_LEGACY,
        load_runs,
        normalise_labels,
        select_controlled_corpus,
        sha256_file,
        validate_provenance,
    )


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "m2_outcomes"

OUTCOME_STATUSES = (
    "positive_commit",
    "zero_commit",
    "no_submission",
    "inconsistent",
)

RAW_LABEL_COLUMNS = (
    "blockchain",
    "mode",
    "workload",
    "dataset",
    "network_size",
)

NUMERIC_COLUMNS = (
    "submit_number",
    "commit_number",
    "average_throughput",
    "average_latency",
    "median_latency",
    "energy",
    "MiB-Rx",
    "MiB-Tx",
)

DERIVED_FLAG_COLUMNS = (
    "submitted_derived",
    "positive_commit_derived",
    "zero_commit_derived",
    "no_submission_derived",
    "inconsistent_derived",
    "tps_valid_positive_commit",
    "latency_valid_positive_commit",
    "energy_valid_observed",
    "energy_valid_positive_commit",
    "network_valid_observed",
)


def prepare_selected_runs(raw: pd.DataFrame) -> pd.DataFrame:
    prepared = raw.copy()
    for column in RAW_LABEL_COLUMNS:
        prepared[f"{column}_raw"] = prepared[column]
    selected = select_controlled_corpus(normalise_labels(prepared))
    validate_provenance(selected)
    return selected


def finite(series: pd.Series) -> pd.Series:
    return series.notna() & np.isfinite(series)


def integer_like(series: pd.Series) -> pd.Series:
    return finite(series) & np.isclose(
        series, np.round(series), rtol=0.0, atol=1e-9
    )


def derive_outcomes(selected: pd.DataFrame) -> pd.DataFrame:
    derived = selected.copy()
    for column in NUMERIC_COLUMNS:
        derived[column] = pd.to_numeric(derived[column], errors="coerce")

    submitted = derived["submit_number"]
    committed = derived["commit_number"]

    inconsistent = (
        ~integer_like(submitted)
        | ~integer_like(committed)
        | (submitted < 0)
        | (committed < 0)
        | (committed > submitted)
        | ((submitted == 0) & (committed > 0))
    )
    no_submission = ~inconsistent & (submitted == 0) & (committed == 0)
    zero_commit = ~inconsistent & (submitted > 0) & (committed == 0)
    positive_commit = ~inconsistent & (submitted > 0) & (committed > 0)

    derived["outcome_status_derived"] = np.select(
        [positive_commit, zero_commit, no_submission],
        ["positive_commit", "zero_commit", "no_submission"],
        default="inconsistent",
    )
    derived["submitted_derived"] = ~inconsistent & (submitted > 0)
    derived["positive_commit_derived"] = positive_commit
    derived["zero_commit_derived"] = zero_commit
    derived["no_submission_derived"] = no_submission
    derived["inconsistent_derived"] = inconsistent

    throughput_available = finite(derived["average_throughput"]) & (
        derived["average_throughput"] >= 0
    )
    latency_available = finite(derived["average_latency"]) & (
        derived["average_latency"] > 0
    )
    energy_available = finite(derived["energy"]) & (derived["energy"] >= 0)
    network_available = (
        finite(derived["MiB-Rx"])
        & finite(derived["MiB-Tx"])
        & (derived["MiB-Rx"] >= 0)
        & (derived["MiB-Tx"] >= 0)
    )

    # A stored TPS value of 0.0 remains eligible when commit_number > 0.  Seven
    # such rows exist because the released TPS field is rounded; M3 recomputes
    # TPS at full precision rather than reclassifying those executions.
    derived["tps_valid_positive_commit"] = positive_commit & throughput_available
    derived["latency_valid_positive_commit"] = positive_commit & latency_available
    derived["energy_valid_observed"] = energy_available
    derived["energy_valid_positive_commit"] = positive_commit & energy_available
    derived["network_valid_observed"] = network_available

    assigned = derived[list(DERIVED_FLAG_COLUMNS[:5])].sum(axis=1)
    if not (assigned == 2).all():
        # Exactly one outcome flag plus submitted_derived for the two submitted
        # outcome states; no-submission and inconsistent have one flag only.
        expected = np.where(derived["submitted_derived"], 2, 1)
        if not np.array_equal(assigned.to_numpy(), expected):
            raise ValueError("Derived outcome flags are not mutually consistent")

    return derived


def configuration_outcome_counts(derived: pd.DataFrame) -> pd.DataFrame:
    counts = (
        derived.groupby(CONFIGURATION_COLUMNS, dropna=False)
        .agg(
            n_observed=("hash", "size"),
            n_submitted=("submitted_derived", "sum"),
            n_positive_commit=("positive_commit_derived", "sum"),
            n_zero_commit=("zero_commit_derived", "sum"),
            n_no_submission=("no_submission_derived", "sum"),
            n_inconsistent=("inconsistent_derived", "sum"),
            n_tps_valid=("tps_valid_positive_commit", "sum"),
            n_latency_valid=("latency_valid_positive_commit", "sum"),
            n_energy_valid_observed=("energy_valid_observed", "sum"),
            n_energy_valid_positive_commit=(
                "energy_valid_positive_commit",
                "sum",
            ),
            n_network_valid_observed=("network_valid_observed", "sum"),
        )
        .reset_index()
    )
    count_columns = [column for column in counts if column.startswith("n_")]
    counts[count_columns] = counts[count_columns].astype(int)
    counts["service_regime_derived"] = np.select(
        [
            counts["n_positive_commit"] == counts["n_observed"],
            counts["n_positive_commit"] == 0,
        ],
        ["all_positive_commit", "no_positive_commit"],
        default="mixed_outcomes",
    )
    return counts.sort_values(CONFIGURATION_COLUMNS, kind="stable").reset_index(
        drop=True
    )


def count_values(series: pd.Series) -> dict[str, int]:
    return {
        str(value): int(count)
        for value, count in series.value_counts(dropna=False).sort_index().items()
    }


def corpus_summary(derived: pd.DataFrame) -> dict[str, object]:
    configurations = configuration_outcome_counts(derived)
    status_counts = derived["outcome_status_derived"].value_counts()
    return {
        "rows": int(len(derived)),
        "configurations": int(len(configurations)),
        "outcome_counts": {
            status: int(status_counts.get(status, 0)) for status in OUTCOME_STATUSES
        },
        "configuration_regimes": count_values(
            configurations["service_regime_derived"]
        ),
        "configurations_with_at_least_9_positive_commits": int(
            (configurations["n_positive_commit"] >= 9).sum()
        ),
        "metric_valid_counts": {
            flag: int(derived[flag].sum())
            for flag in DERIVED_FLAG_COLUMNS[5:]
        },
        "positive_commit_with_stored_tps_zero": int(
            (
                derived["positive_commit_derived"]
                & (derived["average_throughput"] == 0)
            ).sum()
        ),
    }


def build_summary(
    raw: pd.DataFrame, derived: pd.DataFrame, input_path: Path
) -> dict[str, object]:
    try:
        displayed_path = input_path.resolve().relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        displayed_path = input_path.resolve()
    legacy = derived.loc[derived["workload"].isin(PRIMARY_WORKLOADS_LEGACY)]
    return {
        "input": {
            "path": displayed_path.as_posix(),
            "sha256": sha256_file(input_path),
            "rows": int(len(raw)),
        },
        "classification_basis": "released_csv_fields_only",
        "failure_inferred_without_logs": False,
        "selected_six_workload_corpus": corpus_summary(derived),
        "legacy_three_workload_subset": {
            "workloads": PRIMARY_WORKLOADS_LEGACY,
            **corpus_summary(legacy),
        },
    }


def run_derivation(input_path: Path, output_dir: Path | None) -> dict[str, object]:
    raw = load_runs(input_path)
    selected = prepare_selected_runs(raw)
    derived = derive_outcomes(selected)
    summary = build_summary(raw, derived, input_path)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        derived.to_csv(output_dir / "run_outcomes.csv", index=False)
        configuration_outcome_counts(derived).to_csv(
            output_dir / "configuration_outcome_counts.csv", index=False
        )
        (output_dir / "outcome_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Derive observable outcomes and metric-specific masks for M2."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate and print the derivation without writing output files.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = None if args.check_only else args.output_dir
    summary = run_derivation(args.input, output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
