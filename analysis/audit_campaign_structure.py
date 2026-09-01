"""Audit hash-batch structure and descriptive within/between-hash variation (M6)."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
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
DEFAULT_TABLE_PATH = (
    REPOSITORY_ROOT
    / "paper_tables"
    / "six_workloads"
    / "table_campaign_structure.tex"
)
CONFIG = ["blockchain", "mode", "workload", "network_size"]
METRICS = {
    "TPS": ("average_throughput", "tps_point_valid_positive_commit"),
    "Latency": ("average_latency", "latency_valid_positive_commit"),
    "Energy": ("energy", "energy_valid_positive_commit"),
}


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
        "review_point": "M6",
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


def variance_decomposition(derived: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metric, (value_column, eligibility_column) in METRICS.items():
        eligible = derived.loc[derived[eligibility_column]].copy()
        eligible[value_column] = pd.to_numeric(eligible[value_column], errors="raise")
        for config_values, group in eligible.groupby(CONFIG, observed=True):
            values = group[value_column].to_numpy(float)
            overall_mean = float(values.mean())
            total_ss = float(np.square(values - overall_mean).sum())
            hash_groups = list(group.groupby("hash", observed=True, sort=False))
            within_ss = float(
                sum(
                    np.square(
                        batch[value_column].to_numpy(float)
                        - float(batch[value_column].mean())
                    ).sum()
                    for _, batch in hash_groups
                )
            )
            between_ss = float(
                sum(
                    len(batch)
                    * (float(batch[value_column].mean()) - overall_mean) ** 2
                    for _, batch in hash_groups
                )
            )
            hash_sizes = np.asarray([len(batch) for _, batch in hash_groups], dtype=int)
            decomposition_available = len(hash_groups) >= 2 and total_ss > 0
            strict_sensitivity = (
                decomposition_available and int((hash_sizes >= 2).sum()) >= 2
            )
            row = dict(zip(CONFIG, config_values, strict=True))
            row.update(
                {
                    "metric": metric,
                    "eligible_observations": int(len(group)),
                    "eligible_hash_batches": int(len(hash_groups)),
                    "hash_batches_with_at_least_two_eligible_executions": int(
                        (hash_sizes >= 2).sum()
                    ),
                    "total_sum_of_squares": total_ss,
                    "within_hash_sum_of_squares": within_ss,
                    "between_hash_sum_of_squares": between_ss,
                    "decomposition_identity_error": abs(
                        total_ss - within_ss - between_ss
                    ),
                    "between_hash_fraction": (
                        between_ss / total_ss if decomposition_available else np.nan
                    ),
                    "decomposition_available": bool(decomposition_available),
                    "strict_sensitivity": bool(strict_sensitivity),
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)


def summarize_decomposition(table: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metric in METRICS:
        metric_rows = table.loc[table["metric"] == metric]
        available = metric_rows.loc[metric_rows["decomposition_available"]]
        strict = metric_rows.loc[metric_rows["strict_sensitivity"]]
        rows.append(
            {
                "metric": metric,
                "eligible_configurations": int(len(metric_rows)),
                "decomposable_configurations": int(len(available)),
                "strict_configurations": int(len(strict)),
                "between_hash_fraction_q1": float(
                    strict["between_hash_fraction"].quantile(0.25)
                ),
                "between_hash_fraction_median": float(
                    strict["between_hash_fraction"].median()
                ),
                "between_hash_fraction_q3": float(
                    strict["between_hash_fraction"].quantile(0.75)
                ),
                "between_hash_fraction_weighted": float(
                    strict["between_hash_sum_of_squares"].sum()
                    / strict["total_sum_of_squares"].sum()
                ),
            }
        )
    return pd.DataFrame(rows)


def render_table(summary: pd.DataFrame) -> str:
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\color{olive}",
        r"\caption{\vd{M6: Descriptive sensitivity to hash-batch boundaries within configurations. The strict subset requires at least two hash batches that each contain at least two metric-eligible executions. Between-hash shares partition observed sums of squares and are not estimates of a crossed campaign effect because each hash is nested within one configuration.}}",
        r"\label{tab:campaign_hash_sensitivity}",
        r"\small",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{lrrrrrrr}",
        r"\hline",
        r"Metric & Eligible $C$ & Decomposable $C$ & Strict $C$ & Q1 (\%) & Median (\%) & Q3 (\%) & Weighted share (\%) \\",
        r"\hline",
    ]
    for _, row in summary.iterrows():
        lines.append(
            f"{row['metric']} & {int(row['eligible_configurations'])} & "
            f"{int(row['decomposable_configurations'])} & "
            f"{int(row['strict_configurations'])} & "
            f"{100 * row['between_hash_fraction_q1']:.2f} & "
            f"{100 * row['between_hash_fraction_median']:.2f} & "
            f"{100 * row['between_hash_fraction_q3']:.2f} & "
            f"{100 * row['between_hash_fraction_weighted']:.2f} \\\\"
        )
    lines.extend(
        [
            r"\hline",
            r"\end{tabular}",
            r"}",
            r"\vspace{1mm}",
            r"\parbox{\textwidth}{\footnotesize The released corpus contains 1,006 hash batches, each nested within exactly one blockchain--topology--workload--size configuration; 386 are singletons and 620 contain repeated executions. The run index is reused across configurations and therefore is not a campaign identifier. The primary analysis intentionally summarizes all independently reset executions of a fixed configuration; this sensitivity shows how much observed dispersion coincides descriptively with hash-batch boundaries.}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def run(input_path: Path, output_dir: Path, table_path: Path) -> dict[str, object]:
    derived = derive_outcomes(prepare_selected_runs(load_runs(input_path)))
    audit, structure = identifier_audit(derived)
    decomposition = variance_decomposition(derived)
    if decomposition["decomposition_identity_error"].max() > 1e-7:
        raise ValueError("Within/between hash sums of squares do not reconstruct total SS")
    summary = summarize_decomposition(decomposition)

    output_dir.mkdir(parents=True, exist_ok=True)
    table_path.parent.mkdir(parents=True, exist_ok=True)
    (output_dir / "campaign_identifier_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    structure.to_csv(output_dir / "configuration_hash_structure.csv", index=False)
    decomposition.to_csv(output_dir / "campaign_variance_decomposition.csv", index=False)
    summary.to_csv(output_dir / "campaign_variance_summary.csv", index=False)
    table_path.write_text(render_table(summary), encoding="utf-8")

    try:
        generated_table = str(table_path.relative_to(REPOSITORY_ROOT))
    except ValueError:
        generated_table = str(table_path)
    result = {
        "review_point": "M6",
        "identifier_audit": audit,
        "strict_configurations_by_metric": {
            str(row["metric"]): int(row["strict_configurations"])
            for _, row in summary.iterrows()
        },
        "generated_table": generated_table,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--table-path", type=Path, default=DEFAULT_TABLE_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(json.dumps(run(args.input, args.output_dir, args.table_path), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
