"""Audit hash/run/dataset provenance without campaign-level decomposition (R1.6)."""

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
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "m6_campaign_structure"
CONFIG = ["blockchain", "mode", "workload", "network_size"]


def identifier_audit(derived: pd.DataFrame) -> tuple[dict[str, object], pd.DataFrame]:
    hash_config = derived[["hash", *CONFIG]].drop_duplicates()
    configs_per_hash = hash_config.groupby("hash", dropna=False).size()
    hashes_per_config = hash_config.groupby(CONFIG, observed=True).size()
    rows_per_hash = derived.groupby("hash", dropna=False).size()
    run_config = derived[["run", *CONFIG]].drop_duplicates()
    configs_per_run = run_config.groupby("run", dropna=False).size()

    structure = (
        derived.groupby(CONFIG, observed=True)
        .agg(
            observed_executions=("hash", "size"),
            hash_batches=("hash", "nunique"),
            first_timestamp=("start_bench", "min"),
            last_timestamp=("start_bench", "max"),
        )
        .reset_index()
    )
    hash_sizes = derived.groupby([*CONFIG, "hash"], observed=True).size()
    repeated = (
        hash_sizes.ge(2)
        .groupby(level=CONFIG, observed=True)
        .sum()
        .rename("hash_batches_with_at_least_two_executions")
        .reset_index()
    )
    structure = structure.merge(repeated, on=CONFIG, how="left", validate="one_to_one")

    audit = {
        "review_point": "R1.6",
        "observed_executions": int(len(derived)),
        "configuration_cells": int(len(structure)),
        "dataset_values": sorted(str(value) for value in derived["dataset"].unique()),
        "dataset_is_constant": bool(derived["dataset"].nunique(dropna=False) == 1),
        "hash_batches": int(derived["hash"].nunique(dropna=False)),
        "each_hash_maps_to_one_configuration": bool((configs_per_hash == 1).all()),
        "hash_batch_size": {
            "minimum": int(rows_per_hash.min()),
            "median": float(rows_per_hash.median()),
            "maximum": int(rows_per_hash.max()),
        },
        "singleton_hash_batches": int((rows_per_hash == 1).sum()),
        "repeated_hash_batches": int((rows_per_hash >= 2).sum()),
        "hash_batches_per_configuration": {
            "minimum": int(hashes_per_config.min()),
            "median": float(hashes_per_config.median()),
            "maximum": int(hashes_per_config.max()),
        },
        "run_index_values": sorted(int(value) for value in derived["run"].unique()),
        "configurations_per_run_index": {
            "minimum": int(configs_per_run.min()),
            "median": float(configs_per_run.median()),
            "maximum": int(configs_per_run.max()),
        },
        "hash_run_pair_is_unique": bool(
            not derived.duplicated(["hash", "run"], keep=False).any()
        ),
        "distinct_start_timestamps": int(derived["start_bench"].nunique(dropna=False)),
        "interpretation": (
            "hash is a batch identifier nested within one configuration; run is an "
            "index reused across configurations and reset within hash batches; dataset "
            "is constant and cannot identify campaigns"
        ),
    }
    return audit, structure


def run(input_path: Path, output_dir: Path) -> dict[str, object]:
    derived = derive_outcomes(prepare_selected_runs(load_runs(input_path)))
    audit, structure = identifier_audit(derived)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "campaign_identifier_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    structure.to_csv(output_dir / "configuration_hash_structure.csv", index=False)
    result = {
        "review_point": "R1.6",
        "scope": "provenance-only; no within-/between-batch variance decomposition",
        "identifier_audit": audit,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(json.dumps(run(args.input, args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
