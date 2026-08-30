"""Audit the observed repeated-execution design used by the paper.

This module deliberately does not classify outcomes or compute performance
statistics.  It inventories the real rows that remain after the fixed
experimental filters and verifies their provenance structure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import pandas as pd


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "dataset" / "reproducibility-runs.csv"
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "m1_observed_design"

FIXED_FILTERS = {
    "dataset": "2023",
    "link_strategy": "hop",
    "secondaries": 10,
    "cores": 8,
    "ram": 16,
    "dynamic": 0,
}

CONFIGURATION_COLUMNS = [
    "blockchain",
    "mode",
    "workload",
    "cores",
    "ram",
    "secondaries",
    "dataset",
    "link_strategy",
    "network_size",
    "dynamic",
]

PRIMARY_WORKLOADS_LEGACY = ["GAFAM", "PayPal", "VISA"]

REQUIRED_COLUMNS = set(CONFIGURATION_COLUMNS) | {"hash", "run", "start_bench"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_runs(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    return frame


def normalise_labels(frame: pd.DataFrame) -> pd.DataFrame:
    normalised = frame.copy()
    normalised["mode"] = normalised["mode"].str.replace(r"-l$", "", regex=True)
    normalised["mode"] = normalised["mode"].replace({"full-mesh": "full mesh"})
    normalised["dataset"] = normalised["dataset"].replace(
        {"diablo": "2023", "our": "2024"}
    )
    normalised["workload"] = normalised["workload"].replace(
        {
            "10000": "DDoS",
            "dota": "Gaming",
            "football": "FIFA",
            "gafam": "GAFAM",
            "paypal": "PayPal",
            "visa": "VISA",
        }
    )
    normalised["blockchain"] = normalised["blockchain"].replace(
        {
            "algorand": "Algorand",
            "diem": "Diem",
            "poa": "Ethereum",
            "quorum": "Quorum",
            "solana": "Solana",
        }
    )
    normalised["network_size"] = normalised["network_size"].replace(
        {1: "10 nodes", 4: "40 nodes"}
    )
    return normalised


def select_controlled_corpus(frame: pd.DataFrame) -> pd.DataFrame:
    selected = frame.copy()
    for column, expected in FIXED_FILTERS.items():
        selected = selected.loc[selected[column] == expected]
    return selected.copy()


def validate_provenance(frame: pd.DataFrame) -> None:
    missing = frame[["hash", "run", *CONFIGURATION_COLUMNS]].isna().any()
    if missing.any():
        columns = ", ".join(missing.index[missing].tolist())
        raise ValueError(f"Missing provenance/configuration values in: {columns}")

    duplicate_pairs = frame.duplicated(["hash", "run"], keep=False)
    if duplicate_pairs.any():
        pairs = frame.loc[duplicate_pairs, ["hash", "run"]].drop_duplicates()
        raise ValueError(
            f"Duplicate (hash, run) provenance pairs: {len(pairs)}"
        )

    configurations_per_hash = frame.groupby("hash", dropna=False)[
        CONFIGURATION_COLUMNS
    ].apply(lambda group: len(group.drop_duplicates()))
    crossing = configurations_per_hash[configurations_per_hash != 1]
    if not crossing.empty:
        raise ValueError(
            f"Campaign hashes spanning multiple configurations: {len(crossing)}"
        )


def configuration_inventory(frame: pd.DataFrame) -> pd.DataFrame:
    inventory = (
        frame.groupby(CONFIGURATION_COLUMNS, dropna=False)
        .agg(
            n_observed=("hash", "size"),
            n_campaigns=("hash", "nunique"),
            first_observed_at=("start_bench", "min"),
            last_observed_at=("start_bench", "max"),
        )
        .reset_index()
        .sort_values(CONFIGURATION_COLUMNS, kind="stable")
        .reset_index(drop=True)
    )
    return inventory


def campaign_inventory(frame: pd.DataFrame) -> pd.DataFrame:
    aggregations = {
        column: (column, "first") for column in CONFIGURATION_COLUMNS
    }
    aggregations.update(
        {
            "n_observed": ("run", "size"),
            "run_min": ("run", "min"),
            "run_max": ("run", "max"),
            "first_observed_at": ("start_bench", "min"),
            "last_observed_at": ("start_bench", "max"),
        }
    )
    return (
        frame.groupby("hash", dropna=False)
        .agg(**aggregations)
        .reset_index()
        .sort_values([*CONFIGURATION_COLUMNS, "hash"], kind="stable")
        .reset_index(drop=True)
    )


def integer_distribution(values: pd.Series) -> dict[str, int]:
    counts = values.value_counts().sort_index()
    return {str(int(value)): int(count) for value, count in counts.items()}


def subset_summary(frame: pd.DataFrame) -> dict[str, object]:
    inventory = configuration_inventory(frame)
    campaigns_per_configuration = inventory["n_campaigns"]
    campaigns = frame.groupby("hash", dropna=False).size()
    return {
        "rows": int(len(frame)),
        "configurations": int(len(inventory)),
        "campaign_hashes": int(frame["hash"].nunique()),
        "n_observed_min": int(inventory["n_observed"].min()),
        "n_observed_max": int(inventory["n_observed"].max()),
        "n_observed_distribution": integer_distribution(inventory["n_observed"]),
        "campaign_size_distribution": integer_distribution(campaigns),
        "campaigns_per_configuration_distribution": integer_distribution(
            campaigns_per_configuration
        ),
    }


def build_summary(raw: pd.DataFrame, selected: pd.DataFrame, input_path: Path) -> dict[str, object]:
    legacy_primary = selected.loc[
        selected["workload"].isin(PRIMARY_WORKLOADS_LEGACY)
    ]
    run_values = sorted(int(value) for value in selected["run"].unique())
    try:
        displayed_input_path = input_path.resolve().relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        displayed_input_path = input_path.resolve()
    return {
        "input": {
            "path": displayed_input_path.as_posix(),
            "sha256": sha256_file(input_path),
            "rows": int(len(raw)),
            "columns": int(len(raw.columns)),
        },
        "fixed_filters": FIXED_FILTERS,
        "configuration_columns": CONFIGURATION_COLUMNS,
        "selected_corpus": {
            **subset_summary(selected),
            "run_values": run_values,
            "workloads": sorted(selected["workload"].unique().tolist()),
            "blockchains": sorted(selected["blockchain"].unique().tolist()),
            "topologies": sorted(selected["mode"].unique().tolist()),
            "network_sizes": sorted(selected["network_size"].unique().tolist()),
            "first_observed_at": str(selected["start_bench"].min()),
            "last_observed_at": str(selected["start_bench"].max()),
        },
        "legacy_three_workload_subset": {
            "workloads": PRIMARY_WORKLOADS_LEGACY,
            **subset_summary(legacy_primary),
        },
        "interpretation": {
            "primary_unit": "observed execution",
            "campaign_hash_role": "provenance identifier",
            "campaign_hash_is_analysis_factor": False,
            "scheduled_attempt_count_available": False,
            "synthetic_observations_added": False,
        },
    }


def run_audit(input_path: Path, output_dir: Path | None) -> dict[str, object]:
    raw = load_runs(input_path)
    selected = select_controlled_corpus(normalise_labels(raw))
    if selected.empty:
        raise ValueError("The fixed filters selected no rows")
    validate_provenance(selected)
    summary = build_summary(raw, selected, input_path)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        configuration_inventory(selected).to_csv(
            output_dir / "configuration_inventory.csv", index=False
        )
        campaign_inventory(selected).to_csv(
            output_dir / "campaign_inventory.csv", index=False
        )
        (output_dir / "audit_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit observed run counts and campaign provenance for M1."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate and print the audit without writing output files.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = None if args.check_only else args.output_dir
    summary = run_audit(args.input, output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
