"""Run the M1/M3 balanced nine-execution sensitivity analysis.

The primary analysis uses every observed execution.  This sensitivity analysis
instead draws nine *observed* executions per configuration without replacement.
Sampling precedes outcome and metric eligibility checks, so outcome counts and
conditional-performance denominators remain explicit rather than being forced
to nine.  No rows or measurements are synthesized.
"""

from __future__ import annotations

import argparse
import json
import warnings
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
    )
    from .compute_corrected_dispersion import (
        METRICS,
        compute_configuration_table,
    )
    from .derive_run_outcomes import derive_outcomes, prepare_selected_runs
except ImportError:  # Direct execution
    from audit_observed_runs import (  # type: ignore[no-redef]
        CONFIGURATION_COLUMNS,
        DEFAULT_INPUT,
        PRIMARY_WORKLOADS_LEGACY,
        load_runs,
    )
    from compute_corrected_dispersion import (  # type: ignore[no-redef]
        METRICS,
        compute_configuration_table,
    )
    from derive_run_outcomes import (  # type: ignore[no-redef]
        derive_outcomes,
        prepare_selected_runs,
    )


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "balanced_n9"
DEFAULT_REPETITIONS = 5_000
DEFAULT_SEED = 20260830
BALANCED_SAMPLE_SIZE = 9

SENSITIVITY_STATISTICS = (
    "mean",
    "iqr_pct",
    "sample_std_pct",
    "delta_min_pct",
    "delta_max_pct",
    "range_abs",
    "wcd_abs",
    "wcd_pct",
)

FACTOR_COLUMNS = ("blockchain", "mode", "workload", "network_size")


def prepare_configuration_cells(
    derived: pd.DataFrame,
) -> tuple[pd.DataFrame, list[np.ndarray]]:
    """Return sorted configurations and their absolute dataframe row indices."""
    indexed = derived.reset_index(drop=True)
    grouped = indexed.groupby(CONFIGURATION_COLUMNS, sort=True, dropna=False)
    records: list[dict[str, object]] = []
    cells: list[np.ndarray] = []
    for key, positions in grouped.indices.items():
        values = key if isinstance(key, tuple) else (key,)
        records.append(dict(zip(CONFIGURATION_COLUMNS, values, strict=True)))
        cells.append(np.asarray(positions, dtype=np.int64))

    configurations = pd.DataFrame(records)
    observed = np.asarray([len(cell) for cell in cells], dtype=np.int64)
    if len(configurations) == 0:
        raise ValueError("No selected configurations are available")
    if int(observed.min()) < BALANCED_SAMPLE_SIZE:
        raise ValueError(
            "Balanced n=9 sampling requires at least nine observed executions "
            "in every selected configuration"
        )
    configurations["n_observed"] = observed
    return configurations, cells


def draw_balanced_indices(
    cells: list[np.ndarray], repetitions: int, seed: int
) -> list[np.ndarray]:
    """Draw nine real row indices per cell and repetition without replacement."""
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    rng = np.random.default_rng(seed)
    samples: list[np.ndarray] = []
    for cell in cells:
        # Independent random keys yield a uniform sample without replacement.
        keys = rng.random((repetitions, len(cell)))
        local = np.argpartition(
            keys, BALANCED_SAMPLE_SIZE - 1, axis=1
        )[:, :BALANCED_SAMPLE_SIZE]
        samples.append(cell[local])
    return samples


def _metric_statistics_for_samples(
    derived: pd.DataFrame,
    sampled_indices: list[np.ndarray],
    value_column: str,
    eligibility_column: str,
) -> dict[str, np.ndarray]:
    repetitions = sampled_indices[0].shape[0]
    n_cells = len(sampled_indices)
    result = {
        "n_metric": np.zeros((repetitions, n_cells), dtype=np.int16),
        **{
            statistic: np.full((repetitions, n_cells), np.nan, dtype=float)
            for statistic in SENSITIVITY_STATISTICS
        },
    }
    values = pd.to_numeric(derived[value_column], errors="coerce").to_numpy(float)
    eligible = derived[eligibility_column].to_numpy(bool)

    for cell_number, indices in enumerate(sampled_indices):
        selected_values = values[indices]
        selected_eligible = eligible[indices]
        data = np.where(selected_eligible, selected_values, np.nan)
        counts = selected_eligible.sum(axis=1).astype(np.int16)
        result["n_metric"][:, cell_number] = counts

        sums = np.nansum(data, axis=1)
        means = np.divide(
            sums,
            counts,
            out=np.full(repetitions, np.nan),
            where=counts > 0,
        )
        result["mean"][:, cell_number] = means

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            minima = np.nanmin(data, axis=1)
            maxima = np.nanmax(data, axis=1)
            q25, q75 = np.nanquantile(
                data, (0.25, 0.75), axis=1, method="linear"
            )

        centered = data - means[:, None]
        squared = np.nansum(centered * centered, axis=1)
        sample_std = np.sqrt(
            np.divide(
                squared,
                counts - 1,
                out=np.full(repetitions, np.nan),
                where=counts >= 2,
            )
        )
        iqr = q75 - q25
        delta_min = minima - means
        delta_max = maxima - means
        value_range = maxima - minima
        wcd_abs = np.maximum(np.abs(delta_min), np.abs(delta_max))
        positive_mean = means > 0

        def percentage(numerator: np.ndarray) -> np.ndarray:
            return np.divide(
                100.0 * numerator,
                means,
                out=np.full(repetitions, np.nan),
                where=positive_mean,
            )

        result["iqr_pct"][:, cell_number] = percentage(iqr)
        result["sample_std_pct"][:, cell_number] = percentage(sample_std)
        result["delta_min_pct"][:, cell_number] = percentage(delta_min)
        result["delta_max_pct"][:, cell_number] = percentage(delta_max)
        result["range_abs"][:, cell_number] = value_range
        result["wcd_abs"][:, cell_number] = wcd_abs
        result["wcd_pct"][:, cell_number] = percentage(wcd_abs)

    return result


def _summarize_vector(values: np.ndarray) -> dict[str, float | int | None]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {
            "defined_repetitions": 0,
            "median": None,
            "q025": None,
            "q975": None,
            "minimum": None,
            "maximum": None,
        }
    return {
        "defined_repetitions": int(finite.size),
        "median": float(np.median(finite)),
        "q025": float(np.quantile(finite, 0.025)),
        "q975": float(np.quantile(finite, 0.975)),
        "minimum": float(finite.min()),
        "maximum": float(finite.max()),
    }


def denominator_sensitivity_table(
    derived: pd.DataFrame,
    configurations: pd.DataFrame,
    cells: list[np.ndarray],
    sampled_indices: list[np.ndarray],
) -> pd.DataFrame:
    definitions = {
        "n_positive_commit": "positive_commit_derived",
        "n_zero_commit": "zero_commit_derived",
        "n_no_submission": "no_submission_derived",
        **{
            f"n_{metric.name}": metric.eligibility_column for metric in METRICS
        },
    }
    rows: list[dict[str, object]] = []
    for name, column in definitions.items():
        flags = derived[column].to_numpy(bool)
        for cell_number, indices in enumerate(sampled_indices):
            sampled_counts = flags[indices].sum(axis=1).astype(float)
            primary = int(flags[cells[cell_number]].sum())
            rows.append(
                {
                    **configurations.iloc[cell_number][CONFIGURATION_COLUMNS].to_dict(),
                    "denominator": name,
                    "primary_count": primary,
                    **_summarize_vector(sampled_counts),
                }
            )
    return pd.DataFrame(rows)


def configuration_sensitivity_rows(
    configurations: pd.DataFrame,
    primary_table: pd.DataFrame,
    metric_name: str,
    replicate_statistics: dict[str, np.ndarray],
) -> list[dict[str, object]]:
    primary_metric = (
        primary_table.loc[primary_table["metric"] == metric_name]
        .sort_values(CONFIGURATION_COLUMNS, kind="stable")
        .reset_index(drop=True)
    )
    rows: list[dict[str, object]] = []
    for cell_number in range(len(configurations)):
        config = configurations.iloc[cell_number][CONFIGURATION_COLUMNS].to_dict()
        count_summary = _summarize_vector(
            replicate_statistics["n_metric"][:, cell_number].astype(float)
        )
        rows.append(
            {
                **config,
                "metric": metric_name,
                "statistic": "n_metric",
                "primary_value": int(primary_metric.iloc[cell_number]["n_metric"]),
                **count_summary,
            }
        )
        for statistic in SENSITIVITY_STATISTICS:
            rows.append(
                {
                    **config,
                    "metric": metric_name,
                    "statistic": statistic,
                    "primary_value": primary_metric.iloc[cell_number][statistic],
                    **_summarize_vector(
                        replicate_statistics[statistic][:, cell_number]
                    ),
                }
            )
    return rows


def factor_sensitivity_rows(
    configurations: pd.DataFrame,
    primary_table: pd.DataFrame,
    metric_name: str,
    replicate_statistics: dict[str, np.ndarray],
) -> list[dict[str, object]]:
    primary_metric = (
        primary_table.loc[primary_table["metric"] == metric_name]
        .sort_values(CONFIGURATION_COLUMNS, kind="stable")
        .reset_index(drop=True)
    )
    rows: list[dict[str, object]] = []
    scopes = {
        "six_workloads": np.ones(len(configurations), dtype=bool),
        "legacy_three_workloads": configurations["workload"]
        .isin(PRIMARY_WORKLOADS_LEGACY)
        .to_numpy(),
    }
    for scope, scope_mask in scopes.items():
        for factor in FACTOR_COLUMNS:
            for level in configurations.loc[scope_mask, factor].drop_duplicates():
                cell_mask = scope_mask & (configurations[factor].to_numpy() == level)
                for statistic in SENSITIVITY_STATISTICS:
                    primary_values = pd.to_numeric(
                        primary_metric.loc[cell_mask, statistic], errors="coerce"
                    ).to_numpy(float)
                    balanced = replicate_statistics[statistic][:, cell_mask]
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", category=RuntimeWarning)
                        replicate_mean = np.nanmean(balanced, axis=1)
                        replicate_median = np.nanmedian(balanced, axis=1)
                    for aggregation, primary_value, vector in (
                        ("mean", np.nanmean(primary_values), replicate_mean),
                        ("median", np.nanmedian(primary_values), replicate_median),
                    ):
                        rows.append(
                            {
                                "scope": scope,
                                "factor": factor,
                                "level": level,
                                "metric": metric_name,
                                "statistic": statistic,
                                "aggregation": aggregation,
                                "configuration_count": int(cell_mask.sum()),
                                "primary_value": float(primary_value),
                                **_summarize_vector(vector),
                            }
                        )
    return rows


def extrema_sensitivity_rows(
    configurations: pd.DataFrame,
    primary_table: pd.DataFrame,
    metric_name: str,
    replicate_statistics: dict[str, np.ndarray],
) -> list[dict[str, object]]:
    primary_metric = (
        primary_table.loc[primary_table["metric"] == metric_name]
        .sort_values(CONFIGURATION_COLUMNS, kind="stable")
        .reset_index(drop=True)
    )
    definitions = {
        "delta_min_pct": "minimum",
        "delta_max_pct": "maximum",
        "range_abs": "maximum",
        "wcd_abs": "maximum",
        "wcd_pct": "maximum",
    }
    rows: list[dict[str, object]] = []
    scopes = {
        "six_workloads": np.ones(len(configurations), dtype=bool),
        "legacy_three_workloads": configurations["workload"]
        .isin(PRIMARY_WORKLOADS_LEGACY)
        .to_numpy(),
    }
    for scope, scope_mask in scopes.items():
        for statistic, direction in definitions.items():
            matrix = replicate_statistics[statistic][:, scope_mask]
            primary_values = pd.to_numeric(
                primary_metric.loc[scope_mask, statistic], errors="coerce"
            ).to_numpy(float)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=RuntimeWarning)
                if direction == "minimum":
                    vector = np.nanmin(matrix, axis=1)
                    primary_value = np.nanmin(primary_values)
                else:
                    vector = np.nanmax(matrix, axis=1)
                    primary_value = np.nanmax(primary_values)
            rows.append(
                {
                    "scope": scope,
                    "metric": metric_name,
                    "statistic": statistic,
                    "direction": direction,
                    "primary_value": float(primary_value),
                    **_summarize_vector(vector),
                }
            )
    return rows


def eligibility_summary(
    configurations: pd.DataFrame, primary_table: pd.DataFrame
) -> dict[str, object]:
    result: dict[str, object] = {}
    scopes = {
        "six_workloads": np.ones(len(configurations), dtype=bool),
        "legacy_three_workloads": configurations["workload"]
        .isin(PRIMARY_WORKLOADS_LEGACY)
        .to_numpy(),
    }
    for scope, scope_mask in scopes.items():
        metrics: dict[str, object] = {}
        for metric in METRICS:
            metric_table = (
                primary_table.loc[primary_table["metric"] == metric.name]
                .sort_values(CONFIGURATION_COLUMNS, kind="stable")
                .reset_index(drop=True)
            )
            counts = metric_table.loc[scope_mask, "n_metric"]
            metrics[metric.name] = {
                "configurations": int(scope_mask.sum()),
                "configurations_with_at_least_9_metric_values": int(
                    (counts >= BALANCED_SAMPLE_SIZE).sum()
                ),
                "minimum_metric_count": int(counts.min()),
                "maximum_metric_count": int(counts.max()),
            }
        result[scope] = metrics
    return result


def run_sensitivity(
    input_path: Path,
    output_dir: Path | None,
    repetitions: int = DEFAULT_REPETITIONS,
    seed: int = DEFAULT_SEED,
) -> dict[str, object]:
    derived = derive_outcomes(prepare_selected_runs(load_runs(input_path))).reset_index(
        drop=True
    )
    configurations, cells = prepare_configuration_cells(derived)
    sampled_indices = draw_balanced_indices(cells, repetitions, seed)
    primary_table = compute_configuration_table(derived)

    denominator_table = denominator_sensitivity_table(
        derived, configurations, cells, sampled_indices
    )
    configuration_rows: list[dict[str, object]] = []
    factor_rows: list[dict[str, object]] = []
    extrema_rows: list[dict[str, object]] = []
    for metric in METRICS:
        replicate_statistics = _metric_statistics_for_samples(
            derived,
            sampled_indices,
            metric.value_column,
            metric.eligibility_column,
        )
        configuration_rows.extend(
            configuration_sensitivity_rows(
                configurations, primary_table, metric.name, replicate_statistics
            )
        )
        factor_rows.extend(
            factor_sensitivity_rows(
                configurations, primary_table, metric.name, replicate_statistics
            )
        )
        extrema_rows.extend(
            extrema_sensitivity_rows(
                configurations, primary_table, metric.name, replicate_statistics
            )
        )

    configuration_table = pd.DataFrame(configuration_rows)
    factor_table = pd.DataFrame(factor_rows)
    extrema_table = pd.DataFrame(extrema_rows)
    summary = {
        "method": {
            "analysis": "balanced observed-run sensitivity",
            "sampling_unit": "observed execution within configuration",
            "sample_size_per_configuration": BALANCED_SAMPLE_SIZE,
            "without_replacement": True,
            "sampling_before_outcome_and_metric_eligibility": True,
            "repetitions": repetitions,
            "seed": seed,
            "synthetic_rows": 0,
        },
        "selected_configurations": int(len(configurations)),
        "minimum_observed_executions": int(configurations["n_observed"].min()),
        "maximum_observed_executions": int(configurations["n_observed"].max()),
        "eligibility": eligibility_summary(configurations, primary_table),
    }

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        denominator_table.to_csv(
            output_dir / "denominator_sensitivity.csv", index=False
        )
        configuration_table.to_csv(
            output_dir / "configuration_sensitivity.csv", index=False
        )
        factor_table.to_csv(output_dir / "factor_sensitivity.csv", index=False)
        extrema_table.to_csv(output_dir / "extrema_sensitivity.csv", index=False)
        (output_dir / "balanced_sensitivity_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_sensitivity(
        args.input, args.output_dir, args.repetitions, args.seed
    )
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
