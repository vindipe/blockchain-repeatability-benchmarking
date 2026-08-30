"""Bootstrap M4/M7 dispersion estimates and generate standalone LaTeX tables.

Metric-eligible executions are resampled with replacement within each
configuration.  Configuration-level IQR% and sample-Std% are then aggregated
across the remaining factorial dimensions by both the unweighted mean and the
median.  Percentile intervals are propagated through the complete bootstrap
calculation.  The generated LaTeX files are independent ``table*`` environments
that can be included in the manuscript with ``\\input{...}``.
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
    from .balanced_sensitivity import prepare_configuration_cells
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
    from balanced_sensitivity import (  # type: ignore[no-redef]
        prepare_configuration_cells,
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
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "m4_bootstrap"
DEFAULT_TABLE_DIR = REPOSITORY_ROOT / "paper_tables"
DEFAULT_REPETITIONS = 5_000
DEFAULT_SEED = 20260831
INTERVAL_LOWER = 0.025
INTERVAL_UPPER = 0.975

TABLE_METRIC_NAMES = (
    "tps_positive_commit",
    "latency_positive_commit",
    "energy_observed",
)
DISPERSION_STATISTICS = ("iqr_pct", "sample_std_pct")
AGGREGATIONS = ("mean", "median")

FACTOR_SPECS = {
    "topology": ("mode", "Topology"),
    "workload": ("workload", "Workload"),
    "scaling": ("network_size", "Validator set"),
}

METRIC_DISPLAY = {
    "tps_positive_commit": "TPS",
    "latency_positive_commit": "Latency",
    "energy_observed": "Energy",
}

BLOCKCHAIN_LATEX = {
    "Algorand": "Algorand",
    "Diem": "Diem",
    "Ethereum": r"Ethereum~Clique",
    "Quorum": r"Quorum~IBFT",
    "Solana": "Solana",
}


def bootstrap_cell_dispersion(
    values: np.ndarray,
    repetitions: int,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """Bootstrap IQR% and sample-Std% for one metric/configuration cell."""
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if len(clean) < 2:
        return {
            statistic: np.full(repetitions, np.nan, dtype=float)
            for statistic in DISPERSION_STATISTICS
        }

    sampled = clean[rng.integers(0, len(clean), size=(repetitions, len(clean)))]
    means = sampled.mean(axis=1)
    q25, q75 = np.quantile(
        sampled, (0.25, 0.75), axis=1, method="linear"
    )
    sample_std = sampled.std(axis=1, ddof=1)
    positive_mean = means > 0

    def percentage(numerator: np.ndarray) -> np.ndarray:
        return np.divide(
            100.0 * numerator,
            means,
            out=np.full(repetitions, np.nan),
            where=positive_mean,
        )

    return {
        "iqr_pct": percentage(q75 - q25),
        "sample_std_pct": percentage(sample_std),
    }


def bootstrap_metric_matrices(
    derived: pd.DataFrame,
    cells: list[np.ndarray],
    value_column: str,
    eligibility_column: str,
    repetitions: int,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    matrices = {
        statistic: np.full((repetitions, len(cells)), np.nan, dtype=float)
        for statistic in DISPERSION_STATISTICS
    }
    values = pd.to_numeric(derived[value_column], errors="coerce").to_numpy(float)
    eligible = derived[eligibility_column].to_numpy(bool)
    for cell_number, indices in enumerate(cells):
        cell_values = values[indices][eligible[indices]]
        estimates = bootstrap_cell_dispersion(cell_values, repetitions, rng)
        for statistic in DISPERSION_STATISTICS:
            matrices[statistic][:, cell_number] = estimates[statistic]
    return matrices


def percentile_summary(values: np.ndarray) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return float("nan"), float("nan")
    return (
        float(np.quantile(finite, INTERVAL_LOWER)),
        float(np.quantile(finite, INTERVAL_UPPER)),
    )


def configuration_interval_rows(
    configurations: pd.DataFrame,
    primary_metric: pd.DataFrame,
    metric_name: str,
    matrices: dict[str, np.ndarray],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cell_number in range(len(configurations)):
        config = configurations.iloc[cell_number][CONFIGURATION_COLUMNS].to_dict()
        n_metric = int(primary_metric.iloc[cell_number]["n_metric"])
        for statistic in DISPERSION_STATISTICS:
            lower, upper = percentile_summary(matrices[statistic][:, cell_number])
            point = float(primary_metric.iloc[cell_number][statistic])
            if n_metric < 2:
                point = float("nan")
            rows.append(
                {
                    **config,
                    "metric": metric_name,
                    "statistic": statistic,
                    "n_metric": n_metric,
                    "point_estimate": point,
                    "ci_lower": lower,
                    "ci_upper": upper,
                }
            )
    return rows


def factor_interval_rows(
    configurations: pd.DataFrame,
    primary_metric: pd.DataFrame,
    metric_name: str,
    matrices: dict[str, np.ndarray],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    scopes = {
        "six_workloads": np.ones(len(configurations), dtype=bool),
        "legacy_three_workloads": configurations["workload"]
        .isin(PRIMARY_WORKLOADS_LEGACY)
        .to_numpy(),
    }
    for scope, scope_mask in scopes.items():
        for factor_name, (factor_column, _) in FACTOR_SPECS.items():
            scoped_levels = configurations.loc[scope_mask, factor_column].drop_duplicates()
            for blockchain in configurations["blockchain"].drop_duplicates():
                blockchain_mask = configurations["blockchain"].to_numpy() == blockchain
                for level in scoped_levels:
                    level_mask = configurations[factor_column].to_numpy() == level
                    group_mask = scope_mask & blockchain_mask & level_mask
                    total_cells = int(group_mask.sum())
                    for statistic in DISPERSION_STATISTICS:
                        point_values = pd.to_numeric(
                            primary_metric.loc[group_mask, statistic], errors="coerce"
                        ).to_numpy(float)
                        counts = pd.to_numeric(
                            primary_metric.loc[group_mask, "n_metric"], errors="coerce"
                        ).to_numpy(int)
                        defined = np.isfinite(point_values) & (counts >= 2)
                        bootstrap_values = matrices[statistic][:, group_mask]
                        bootstrap_values = bootstrap_values[:, defined]
                        point_values = point_values[defined]
                        counts = counts[defined]
                        if defined.any():
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore", category=RuntimeWarning)
                                replicate_aggregates = {
                                    "mean": np.nanmean(bootstrap_values, axis=1),
                                    "median": np.nanmedian(bootstrap_values, axis=1),
                                }
                        else:
                            replicate_aggregates = {
                                aggregation: np.full(
                                    matrices[statistic].shape[0], np.nan
                                )
                                for aggregation in AGGREGATIONS
                            }
                        for aggregation in AGGREGATIONS:
                            if not defined.any():
                                point = float("nan")
                            elif aggregation == "mean":
                                point = float(np.nanmean(point_values))
                            else:
                                point = float(np.nanmedian(point_values))
                            lower, upper = percentile_summary(
                                replicate_aggregates[aggregation]
                            )
                            rows.append(
                                {
                                    "scope": scope,
                                    "factor": factor_name,
                                    "factor_column": factor_column,
                                    "blockchain": blockchain,
                                    "level": level,
                                    "metric": metric_name,
                                    "statistic": statistic,
                                    "aggregation": aggregation,
                                    "total_configuration_cells": total_cells,
                                    "contributing_configuration_cells": int(defined.sum()),
                                    "metric_observations": int(counts.sum()),
                                    "minimum_n_metric": int(counts.min())
                                    if counts.size
                                    else 0,
                                    "maximum_n_metric": int(counts.max())
                                    if counts.size
                                    else 0,
                                    "point_estimate": point,
                                    "ci_lower": lower,
                                    "ci_upper": upper,
                                }
                            )
    return rows


def latex_level(value: object, factor_name: str) -> str:
    text = str(value)
    if factor_name == "scaling":
        return text.replace(" nodes", "")
    return text.replace("_", r"\_")


def latex_estimate(row: pd.Series) -> str:
    if not np.isfinite(
        row[["point_estimate", "ci_lower", "ci_upper"]].to_numpy(float)
    ).all():
        return r"--"
    return (
        f"{row['point_estimate']:.2f} "
        f"[{row['ci_lower']:.2f}, {row['ci_upper']:.2f}]"
    )


def render_latex_table(
    factor_table: pd.DataFrame,
    scope: str,
    factor_name: str,
    metric_name: str,
    repetitions: int,
    seed: int,
) -> str:
    _, factor_display = FACTOR_SPECS[factor_name]
    metric_display = METRIC_DISPLAY[metric_name]
    selected = factor_table.loc[
        (factor_table["scope"] == scope)
        & (factor_table["factor"] == factor_name)
        & (factor_table["metric"] == metric_name)
    ]
    index_columns = [
        "blockchain",
        "level",
        "total_configuration_cells",
        "contributing_configuration_cells",
        "metric_observations",
        "minimum_n_metric",
        "maximum_n_metric",
    ]
    table_rows = selected[index_columns].drop_duplicates().reset_index(drop=True)

    # Both scope directories expose the same manuscript-facing labels. Only one
    # generated set is included at a time, so switching from the legacy check
    # to the six-workload analysis requires replacing files, not paper markup.
    label = f"tab:repeatability_{factor_name}_{metric_name.split('_')[0]}"
    workload_text = "six workloads" if scope == "six_workloads" else "GAFAM, PayPal, and VISA"
    lines = [
        "% Auto-generated by analysis/bootstrap_dispersion_tables.py; do not edit.",
        r"\begin{table*}[t]",
        r"\centering",
        r"\scriptsize",
        (
            rf"\caption{{{factor_display}-conditioned {metric_display} dispersion "
            rf"across {workload_text}. Values are point estimates with 95\% "
            rf"percentile bootstrap intervals from {repetitions:,} within-configuration "
            rf"replicates (seed {seed}). Mean and median are unweighted across "
            rf"configuration cells. $C$ is the number of contributing cells and "
            rf"$n_{{c,k}}$ is their metric-eligible run-count range.}}"
        ),
        rf"\label{{{label}}}",
        r"\adjustbox{max width=\textwidth}{%",
        r"\begin{tabular}{llrrrllll}",
        r"\toprule",
        (
            rf"\textbf{{Blockchain}} & \textbf{{{factor_display}}} & "
            r"\textbf{$C$} & \textbf{$N_k$} & \textbf{$n_{c,k}$} & "
            r"\textbf{Mean IQR\%} & \textbf{Median IQR\%} & "
            r"\textbf{Mean Std\%} & \textbf{Median Std\%} \\"
        ),
        r"\midrule",
    ]
    blockchain_order = list(BLOCKCHAIN_LATEX)
    table_rows["_blockchain_order"] = table_rows["blockchain"].map(
        {name: number for number, name in enumerate(blockchain_order)}
    )
    table_rows = table_rows.sort_values(
        ["_blockchain_order", "level"], kind="stable"
    )
    previous_blockchain: str | None = None
    for _, row in table_rows.iterrows():
        blockchain = str(row["blockchain"])
        if previous_blockchain is not None and blockchain != previous_blockchain:
            lines.append(r"\midrule")
        previous_blockchain = blockchain

        def cell(statistic: str, aggregation: str) -> str:
            match = selected.loc[
                (selected["blockchain"] == row["blockchain"])
                & (selected["level"] == row["level"])
                & (selected["statistic"] == statistic)
                & (selected["aggregation"] == aggregation)
            ]
            if len(match) != 1:
                raise ValueError(
                    "Expected one factor estimate for each statistic/aggregation"
                )
            return latex_estimate(match.iloc[0])

        contributing = int(row["contributing_configuration_cells"])
        n_range = (
            f"{int(row['minimum_n_metric'])}--"
            f"{int(row['maximum_n_metric'])}"
            if contributing
            else r"--"
        )
        lines.append(
            " & ".join(
                (
                    BLOCKCHAIN_LATEX[blockchain],
                    latex_level(row["level"], factor_name),
                    str(contributing),
                    str(int(row["metric_observations"])),
                    n_range,
                    cell("iqr_pct", "mean"),
                    cell("iqr_pct", "median"),
                    cell("sample_std_pct", "mean"),
                    cell("sample_std_pct", "median"),
                )
            )
            + r" \\"
        )
    lines.extend(
        (
            r"\bottomrule",
            r"\end{tabular}%",
            r"}",
            r"\end{table*}",
            "",
        )
    )
    return "\n".join(lines)


def validate_factor_table(table: pd.DataFrame) -> None:
    if table.empty:
        raise ValueError("No factor-level bootstrap results were produced")
    defined = table["contributing_configuration_cells"] > 0
    numeric = table.loc[defined, ["point_estimate", "ci_lower", "ci_upper"]]
    if not np.isfinite(numeric.to_numpy(float)).all():
        raise ValueError("A defined factor-level row contains an undefined estimate")
    if (table.loc[defined, "ci_lower"] > table.loc[defined, "ci_upper"]).any():
        raise ValueError("A bootstrap interval has reversed limits")
    undefined = table.loc[~defined, ["point_estimate", "ci_lower", "ci_upper"]]
    if np.isfinite(undefined.to_numpy(float)).any():
        raise ValueError("An empty factor-level row has a numerical estimate")


def run_bootstrap(
    input_path: Path,
    output_dir: Path | None,
    repetitions: int = DEFAULT_REPETITIONS,
    seed: int = DEFAULT_SEED,
    table_dir: Path | None = None,
) -> dict[str, object]:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    derived = derive_outcomes(prepare_selected_runs(load_runs(input_path))).reset_index(
        drop=True
    )
    configurations, cells = prepare_configuration_cells(derived)
    primary = compute_configuration_table(derived)
    rng = np.random.default_rng(seed)

    configuration_rows: list[dict[str, object]] = []
    factor_rows: list[dict[str, object]] = []
    for metric in METRICS:
        if metric.name not in TABLE_METRIC_NAMES:
            continue
        primary_metric = (
            primary.loc[primary["metric"] == metric.name]
            .sort_values(CONFIGURATION_COLUMNS, kind="stable")
            .reset_index(drop=True)
        )
        matrices = bootstrap_metric_matrices(
            derived,
            cells,
            metric.value_column,
            metric.eligibility_column,
            repetitions,
            rng,
        )
        configuration_rows.extend(
            configuration_interval_rows(
                configurations, primary_metric, metric.name, matrices
            )
        )
        factor_rows.extend(
            factor_interval_rows(
                configurations, primary_metric, metric.name, matrices
            )
        )

    configuration_table = pd.DataFrame(configuration_rows)
    factor_table = pd.DataFrame(factor_rows)
    validate_factor_table(factor_table)

    generated_tables: list[str] = []
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        configuration_table.to_csv(
            output_dir / "configuration_bootstrap_intervals.csv", index=False
        )
        factor_table.to_csv(output_dir / "factor_bootstrap_summary.csv", index=False)
    latex_root = table_dir if table_dir is not None else output_dir
    if latex_root is not None:
        for scope in ("six_workloads", "legacy_three_workloads"):
            scope_table_dir = latex_root / scope
            scope_table_dir.mkdir(parents=True, exist_ok=True)
            for factor_name in FACTOR_SPECS:
                for metric_name in TABLE_METRIC_NAMES:
                    filename = f"table_{factor_name}_{metric_name.split('_')[0]}.tex"
                    path = scope_table_dir / filename
                    path.write_text(
                        render_latex_table(
                            factor_table,
                            scope,
                            factor_name,
                            metric_name,
                            repetitions,
                            seed,
                        ),
                        encoding="utf-8",
                    )
                    try:
                        displayed = path.relative_to(REPOSITORY_ROOT)
                    except ValueError:
                        displayed = path
                    generated_tables.append(displayed.as_posix())

    summary = {
        "method": {
            "bootstrap_unit": "metric-eligible observed execution within configuration",
            "resampling": "with replacement at the original metric-specific cell size",
            "interval": "percentile",
            "confidence_level": 0.95,
            "repetitions": repetitions,
            "seed": seed,
            "configuration_aggregation": ["unweighted mean", "median"],
            "minimum_metric_count_for_dispersion": 2,
        },
        "configuration_cells": int(len(configurations)),
        "metrics": list(TABLE_METRIC_NAMES),
        "generated_latex_tables": generated_tables,
    }
    if output_dir is not None:
        (output_dir / "bootstrap_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--table-dir",
        type=Path,
        default=DEFAULT_TABLE_DIR,
        help="Directory for standalone manuscript table files.",
    )
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_bootstrap(
        args.input,
        args.output_dir,
        args.repetitions,
        args.seed,
        table_dir=args.table_dir,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
