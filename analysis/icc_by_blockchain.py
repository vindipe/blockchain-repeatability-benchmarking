"""Estimate log-scale ICCs within each blockchain (S1/R2.4).

For every blockchain and positive-service metric, an intercept-only mixed model
uses configuration as a random intercept.  ICC is the between-configuration
variance divided by total variance.  Configuration-cluster bootstrap intervals
resample complete configuration groups, relabelling duplicates so that no
synthetic cross-configuration group is created.
"""

from __future__ import annotations

import argparse
import json
import warnings
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

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
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "icc_by_blockchain"
DEFAULT_TABLE_DIR = REPOSITORY_ROOT / "paper_tables"
DEFAULT_REPETITIONS = 1_000
DEFAULT_SEED = 20260901

METRIC_SPECS = {
    "TPS": ("average_throughput", "tps_point_valid_positive_commit"),
    "Latency": ("average_latency", "latency_valid_positive_commit"),
    "Energy": ("energy", "energy_valid_positive_commit"),
}


def fit_random_intercept(values: np.ndarray, groups: np.ndarray) -> dict[str, object]:
    exog = np.ones((len(values), 1), dtype=float)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = sm.MixedLM(values, exog, groups=groups).fit(
            reml=True, method="lbfgs", maxiter=300, disp=False
        )
    between = float(result.cov_re[0, 0])
    within = float(result.scale)
    total = between + within
    return {
        "icc": between / total if total > 0 else np.nan,
        "between_configuration_variance": between,
        "within_configuration_variance": within,
        "converged": bool(result.converged),
        "warnings": sorted({str(item.message) for item in caught}),
    }


def cluster_bootstrap(
    values: np.ndarray,
    groups: np.ndarray,
    repetitions: int,
    seed: int,
) -> tuple[np.ndarray, int]:
    rng = np.random.default_rng(seed)
    unique_groups = np.unique(groups)
    indices = {group: np.flatnonzero(groups == group) for group in unique_groups}
    estimates = np.full(repetitions, np.nan, dtype=float)
    failures = 0
    for repetition in range(repetitions):
        sampled = rng.choice(unique_groups, size=len(unique_groups), replace=True)
        selected = []
        relabelled = []
        for new_group, old_group in enumerate(sampled):
            group_indices = indices[old_group]
            selected.append(group_indices)
            relabelled.append(np.full(len(group_indices), new_group, dtype=int))
        bootstrap_values = values[np.concatenate(selected)]
        bootstrap_groups = np.concatenate(relabelled)
        try:
            estimate = fit_random_intercept(bootstrap_values, bootstrap_groups)
            if estimate["converged"] and np.isfinite(estimate["icc"]):
                estimates[repetition] = float(estimate["icc"])
            else:
                failures += 1
        except (ValueError, np.linalg.LinAlgError):
            failures += 1
    return estimates, failures


def prepare_model_data(
    data: pd.DataFrame, blockchain: str, metric: str
) -> tuple[np.ndarray, np.ndarray, int]:
    value_column, eligibility_column = METRIC_SPECS[metric]
    selected = data.loc[
        (data["blockchain"] == blockchain) & data[eligibility_column]
    ].copy()
    selected["configuration_id"] = selected[CONFIGURATION_COLUMNS].astype(str).agg(
        "|".join, axis=1
    )
    values = np.log(pd.to_numeric(selected[value_column]).to_numpy(float))
    groups, _ = pd.factorize(selected["configuration_id"], sort=True)
    return values, groups.astype(int), int(selected["configuration_id"].nunique())


def bootstrap_job(args: tuple[object, ...]) -> dict[str, object]:
    scope, blockchain, metric, values, groups, configuration_count, repetitions, seed = args
    point = fit_random_intercept(values, groups)
    estimates, failures = cluster_bootstrap(values, groups, repetitions, seed)
    finite = estimates[np.isfinite(estimates)]
    if len(finite) < max(1, int(np.ceil(0.8 * repetitions))):
        raise RuntimeError(
            f"Too few converged bootstrap fits for {scope}/{blockchain}/{metric}: "
            f"{len(finite)}/{repetitions}"
        )
    return {
        "scope": scope,
        "blockchain": blockchain,
        "metric": metric,
        "n_observations": int(len(values)),
        "n_configurations": configuration_count,
        **point,
        "ci_lower": float(np.quantile(finite, 0.025)),
        "ci_upper": float(np.quantile(finite, 0.975)),
        "bootstrap_repetitions": repetitions,
        "bootstrap_converged": int(len(finite)),
        "bootstrap_failures": failures,
        "seed": seed,
    }


def render_icc_table(table: pd.DataFrame, repetitions: int, seed: int) -> str:
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Within-blockchain log-scale random-intercept ICC estimates. Brackets give 95\% configuration-cluster bootstrap intervals.}",
        r"\label{tab:icc_by_blockchain}",
        r"\small",
        r"\begin{tabular}{lccc}",
        r"\hline",
        r"Blockchain & TPS ICC [95\% CI] & Latency ICC [95\% CI] & Energy ICC [95\% CI] \\",
        r"\hline",
    ]
    for blockchain in sorted(table["blockchain"].unique()):
        cells = [blockchain.replace("Ethereum", "Ethereum~Clique").replace("Quorum", "Quorum~IBFT")]
        for metric in METRIC_SPECS:
            row = table.loc[
                (table["blockchain"] == blockchain) & (table["metric"] == metric)
            ].iloc[0]
            cells.append(
                f"{row['icc']:.3f} [{row['ci_lower']:.3f}, {row['ci_upper']:.3f}]"
            )
        lines.append(" & ".join(cells) + r" \\")
    lines.extend(
        [
            r"\hline",
            r"\end{tabular}",
            rf"\parbox{{\textwidth}}{{\footnotesize REML random-intercept models use configuration as the grouping factor and positive-service observations on the natural-log scale. Intervals use {repetitions:,} cluster-bootstrap replicates from deterministic streams beginning at seed {seed}.}}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def run_icc(
    input_path: Path,
    output_dir: Path,
    table_dir: Path,
    repetitions: int = DEFAULT_REPETITIONS,
    seed: int = DEFAULT_SEED,
    workers: int | None = None,
) -> dict[str, object]:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    derived = derive_outcomes(prepare_selected_runs(load_runs(input_path)))
    blockchains = sorted(derived["blockchain"].unique())
    jobs = []
    job_number = 0
    for scope in ("legacy_three_workloads", "six_workloads"):
        data = (
            derived.loc[derived["workload"].isin(PRIMARY_WORKLOADS_LEGACY)].copy()
            if scope == "legacy_three_workloads"
            else derived.copy()
        )
        for blockchain in blockchains:
            for metric in METRIC_SPECS:
                values, groups, configuration_count = prepare_model_data(
                    data, blockchain, metric
                )
                jobs.append(
                    (
                        scope,
                        blockchain,
                        metric,
                        values,
                        groups,
                        configuration_count,
                        repetitions,
                        seed + job_number,
                    )
                )
                job_number += 1

    results = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(bootstrap_job, job) for job in jobs]
        for future in as_completed(futures):
            results.append(future.result())
    table = pd.DataFrame(results).sort_values(
        ["scope", "blockchain", "metric"], kind="stable"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(output_dir / "icc_by_blockchain.csv", index=False)
    for scope in ("legacy_three_workloads", "six_workloads"):
        scope_output = output_dir / scope
        scope_output.mkdir(parents=True, exist_ok=True)
        selected = table.loc[table["scope"] == scope].copy()
        selected.to_csv(scope_output / "icc_by_blockchain.csv", index=False)
        scope_tables = table_dir / scope
        scope_tables.mkdir(parents=True, exist_ok=True)
        (scope_tables / "table_icc_by_blockchain.tex").write_text(
            render_icc_table(selected, repetitions, seed), encoding="utf-8"
        )
    summary = {
        "method": "REML intercept-only mixed model on log metric",
        "group": "configuration within blockchain",
        "interval": "95% configuration-cluster percentile bootstrap",
        "repetitions": repetitions,
        "base_seed": seed,
        "models": int(len(table)),
        "bootstrap_failures": int(table["bootstrap_failures"].sum()),
        "minimum_converged_bootstrap_replicates": int(table["bootstrap_converged"].min()),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--table-dir", type=Path, default=DEFAULT_TABLE_DIR)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--workers", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_icc(
        args.input,
        args.output_dir,
        args.table_dir,
        repetitions=args.repetitions,
        seed=args.seed,
        workers=args.workers,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
