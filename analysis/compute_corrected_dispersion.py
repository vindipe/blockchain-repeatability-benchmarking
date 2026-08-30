"""Compute M3 configuration-level dispersion with symmetric eligibility.

Every statistic for a metric/configuration pair is computed from exactly the
same eligible observations.  Outcome accounting remains separate.  The script
also verifies the algebraic bounds on signed relative deviations and uses the
sample standard deviation (``ddof=1``).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
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
    from .derive_run_outcomes import derive_outcomes, prepare_selected_runs
except ImportError:  # Direct execution
    from audit_observed_runs import (  # type: ignore[no-redef]
        CONFIGURATION_COLUMNS,
        DEFAULT_INPUT,
        PRIMARY_WORKLOADS_LEGACY,
        load_runs,
    )
    from derive_run_outcomes import (  # type: ignore[no-redef]
        derive_outcomes,
        prepare_selected_runs,
    )


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "m3_dispersion"


@dataclass(frozen=True)
class MetricSpec:
    name: str
    value_column: str
    eligibility_column: str
    unit: str


METRICS = (
    MetricSpec(
        "tps_positive_commit",
        "average_throughput",
        "tps_point_valid_positive_commit",
        "TPS",
    ),
    MetricSpec(
        "latency_positive_commit",
        "average_latency",
        "latency_valid_positive_commit",
        "s",
    ),
    MetricSpec(
        "energy_observed",
        "energy",
        "energy_valid_observed",
        "kWh",
    ),
    MetricSpec(
        "energy_positive_commit",
        "energy",
        "energy_valid_positive_commit",
        "kWh",
    ),
)


def sample_std(values: pd.Series) -> float:
    """Sample standard deviation; undefined for fewer than two observations."""
    if len(values) < 2:
        return float("nan")
    return float(values.std(ddof=1))


def configuration_statistics(values: pd.Series) -> dict[str, float | int]:
    clean = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    n = int(len(clean))
    if n == 0:
        return {
            "n_metric": 0,
            **{name: float("nan") for name in STATISTIC_COLUMNS},
        }

    mean = float(clean.mean())
    minimum = float(clean.min())
    maximum = float(clean.max())
    q25 = float(clean.quantile(0.25, interpolation="linear"))
    q75 = float(clean.quantile(0.75, interpolation="linear"))
    std = sample_std(clean)
    delta_min = minimum - mean
    delta_max = maximum - mean
    iqr = q75 - q25
    value_range = maximum - minimum

    if mean > 0:
        delta_min_pct = 100.0 * delta_min / mean
        delta_max_pct = 100.0 * delta_max / mean
        iqr_pct = 100.0 * iqr / mean
        std_pct = 100.0 * std / mean if np.isfinite(std) else float("nan")
    else:
        delta_min_pct = float("nan")
        delta_max_pct = float("nan")
        iqr_pct = float("nan")
        std_pct = float("nan")

    return {
        "n_metric": n,
        "mean": mean,
        "minimum": minimum,
        "maximum": maximum,
        "q25": q25,
        "q75": q75,
        "sample_std": std,
        "iqr": iqr,
        "iqr_pct": iqr_pct,
        "sample_std_pct": std_pct,
        "delta_min": delta_min,
        "delta_max": delta_max,
        "delta_min_pct": delta_min_pct,
        "delta_max_pct": delta_max_pct,
        "range_abs": value_range,
        "wcd_abs": max(abs(delta_min), abs(delta_max)),
        "wcd_pct": max(abs(delta_min_pct), abs(delta_max_pct))
        if np.isfinite(delta_min_pct) and np.isfinite(delta_max_pct)
        else float("nan"),
    }


STATISTIC_COLUMNS = (
    "mean",
    "minimum",
    "maximum",
    "q25",
    "q75",
    "sample_std",
    "iqr",
    "iqr_pct",
    "sample_std_pct",
    "delta_min",
    "delta_max",
    "delta_min_pct",
    "delta_max_pct",
    "range_abs",
    "wcd_abs",
    "wcd_pct",
)


def compute_configuration_table(derived: pd.DataFrame) -> pd.DataFrame:
    configurations = (
        derived[CONFIGURATION_COLUMNS]
        .drop_duplicates()
        .sort_values(CONFIGURATION_COLUMNS, kind="stable")
    )
    rows: list[dict[str, object]] = []
    for config_values in configurations.itertuples(index=False, name=None):
        config = dict(zip(CONFIGURATION_COLUMNS, config_values, strict=True))
        mask = pd.Series(True, index=derived.index)
        for column, value in config.items():
            mask &= derived[column] == value
        cell = derived.loc[mask]

        for metric in METRICS:
            eligible = cell.loc[cell[metric.eligibility_column], metric.value_column]
            stats = configuration_statistics(eligible)
            row: dict[str, object] = {
                **config,
                "metric": metric.name,
                "unit": metric.unit,
                "value_column": metric.value_column,
                "eligibility_column": metric.eligibility_column,
                "n_observed": int(len(cell)),
                "n_positive_commit": int(cell["positive_commit_derived"].sum()),
                "n_zero_commit": int(cell["zero_commit_derived"].sum()),
                "n_no_submission": int(cell["no_submission_derived"].sum()),
                "n_tps_censored": int(cell["tps_censored_positive_commit"].sum()),
                **stats,
            }
            rows.append(row)

    table = pd.DataFrame(rows)
    validate_configuration_table(table)
    return table


def validate_configuration_table(table: pd.DataFrame) -> None:
    defined = table.loc[(table["n_metric"] > 0) & (table["mean"] > 0)]
    tolerance = 1e-9
    if (defined["delta_min_pct"] < -100.0 - tolerance).any():
        raise ValueError("A downward relative deviation is below the -100% bound")
    upward_bound = 100.0 * (defined["n_metric"] - 1)
    if (defined["delta_max_pct"] > upward_bound + tolerance).any():
        raise ValueError("An upward relative deviation exceeds 100(n-1)%")
    if not np.allclose(
        defined["range_abs"],
        defined["maximum"] - defined["minimum"],
        rtol=0.0,
        atol=tolerance,
    ):
        raise ValueError("Absolute ranges do not match maximum - minimum")


def finite_or_none(value: object) -> object:
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def scope_summary(table: pd.DataFrame) -> dict[str, object]:
    result: dict[str, object] = {}
    for metric, group in table.groupby("metric", sort=False):
        estimable = group.loc[group["n_metric"] > 0]
        maxima: dict[str, object] = {}
        for column in ("range_abs", "wcd_abs", "delta_min_pct", "delta_max_pct", "wcd_pct"):
            series = estimable[column].dropna()
            if series.empty:
                maxima[column] = None
                continue
            index = series.abs().idxmax() if column == "delta_min_pct" else series.idxmax()
            row = estimable.loc[index]
            maxima[column] = {
                "value": finite_or_none(row[column]),
                "blockchain": row["blockchain"],
                "topology": row["mode"],
                "workload": row["workload"],
                "network_size": row["network_size"],
                "n_metric": int(row["n_metric"]),
            }
        result[metric] = {
            "configuration_rows": int(len(group)),
            "estimable_configurations": int((group["n_metric"] > 0).sum()),
            "configurations_with_sample_std": int((group["n_metric"] >= 2).sum()),
            "metric_observations": int(group["n_metric"].sum()),
            "maxima": maxima,
        }
    return result


def build_summary(derived: pd.DataFrame, table: pd.DataFrame) -> dict[str, object]:
    legacy = table.loc[table["workload"].isin(PRIMARY_WORKLOADS_LEGACY)]
    return {
        "method": {
            "eligibility": "one metric-specific mask for every statistic",
            "sample_standard_deviation_ddof": 1,
            "relative_deviation": "100 * (y - configuration_mean) / configuration_mean",
            "tps_rounding": {
                "source_export_precision_decimal_places": 1,
                "exact_last_event_time_available": False,
                "positive_commit_left_censored_rows": int(
                    derived["tps_censored_positive_commit"].sum()
                ),
                "handling": "retained as positive-commit outcomes; excluded from point-valued TPS statistics",
            },
        },
        "selected_six_workload_corpus": scope_summary(table),
        "legacy_three_workload_subset": {
            "workloads": PRIMARY_WORKLOADS_LEGACY,
            **scope_summary(legacy),
        },
    }


def run_analysis(input_path: Path, output_dir: Path | None) -> dict[str, object]:
    raw = load_runs(input_path)
    derived = derive_outcomes(prepare_selected_runs(raw))
    table = compute_configuration_table(derived)
    summary = build_summary(derived, table)
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        table.to_csv(output_dir / "configuration_metric_statistics.csv", index=False)
        (output_dir / "dispersion_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_analysis(args.input, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
