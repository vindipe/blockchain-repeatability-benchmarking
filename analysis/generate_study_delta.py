"""Generate the audited ACM-DLT versus IEEE Access study-delta records."""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "m8_study_delta"
ACM_DOI = "10.1145/3828757"

ROWS = [
    {
        "area": "Article scope",
        "published_in_acm_dlt": (
            "Integrated topology-aware performance, network-perturbation, energy, "
            "and compact repeatability/P2 assessment."
        ),
        "new_in_ieee_access": (
            "Dedicated configuration- and run-level P2 study of experimental "
            "repeatability and operational performance predictability."
        ),
    },
    {
        "area": "Shared baseline (not new)",
        "published_in_acm_dlt": (
            "Lilith/Diablo/Kollaps, the released experimental design and corpus, "
            r"P0--P3, IQR\%, Std\%, WCD, factorial ANOVA, and ICC."
        ),
        "new_in_ieee_access": (
            "Reused explicitly as prior work and baseline; none of these elements is "
            "claimed as an IEEE contribution."
        ),
    },
    {
        "area": "Analytical coverage",
        "published_in_acm_dlt": (
            "Compact P2 analysis based on three canonical workloads and a fixed "
            "ten-run budget, with aggregate blockchain/factor views."
        ),
        "new_in_ieee_access": (
            "Complete six-workload corpus: 4,080 observed executions, 300 fully "
            "crossed configurations, and 9--26 observed executions per cell."
        ),
    },
    {
        "area": "Outcome and metric eligibility",
        "published_in_acm_dlt": (
            "Metric-centred aggregate treatment; service incidence is not modeled "
            "separately from conditional performance."
        ),
        "new_in_ieee_access": (
            "Audited positive-commit, zero-commit, and no-submission states; "
            "metric-specific eligibility; separate service-incidence and "
            "conditional-performance components."
        ),
    },
    {
        "area": "Factorial and consistency models",
        "published_in_acm_dlt": (
            "Raw-scale factorial ANOVA and a single pooled ICC provide global "
            "variance attribution."
        ),
        "new_in_ieee_access": (
            "Two-part models; log-scale HC3 inference; all two-way and targeted "
            "three-way interactions; within-blockchain log-scale ICCs with "
            "configuration-cluster bootstrap intervals."
        ),
    },
    {
        "area": "Uncertainty and sensitivity",
        "published_in_acm_dlt": (
            "Point dispersion and observed extrema; additional repetitions and "
            "stronger tail characterization are left to future work."
        ),
        "new_in_ieee_access": (
            "5,000-repetition dispersion bootstrap, balanced nine-execution "
            "sensitivity over every cell."
        ),
    },
    {
        "area": "Result resolution and guidance",
        "published_in_acm_dlt": (
            "Aggregate topology/performance/energy trade-offs and blockchain-level "
            "repeatability headlines."
        ),
        "new_in_ieee_access": (
            "Outcome-aware factor-conditioned and run-level evidence, corrected "
            "tails, conditional topology/scale effects, and practical guidance for "
            "variance-aware comparisons."
        ),
    },
]


def validate_evidence() -> dict[str, object]:
    workload_summary = json.loads(
        (REPOSITORY_ROOT / "outputs/revision/m1_workloads/summary.json").read_text(
            encoding="utf-8"
        )
    )
    balanced_summary = json.loads(
        (
            REPOSITORY_ROOT
            / "outputs/revision/balanced_n9/balanced_sensitivity_summary.json"
        ).read_text(encoding="utf-8")
    )
    icc_summary = json.loads(
        (REPOSITORY_ROOT / "outputs/revision/icc_by_blockchain/summary.json").read_text(
            encoding="utf-8"
        )
    )

    expected = {
        "workloads": 6,
        "configuration_cells": 300,
        "observed_executions": 4080,
        "minimum_observed_per_cell": 9,
        "maximum_observed_per_cell": 26,
    }
    for key, value in expected.items():
        if workload_summary.get(key) != value:
            raise ValueError(f"M8 evidence mismatch for {key}: {workload_summary.get(key)}")
    if balanced_summary.get("method", {}).get("sample_size_per_configuration") != 9:
        raise ValueError("M8 requires the completed balanced n=9 sensitivity")
    if balanced_summary.get("method", {}).get("repetitions") != 5000:
        raise ValueError("M8 requires 5,000 balanced sensitivity repetitions")
    if icc_summary.get("repetitions") != 1000:
        raise ValueError("M8 requires the completed 1,000-repetition ICC bootstrap")
    return {
        **expected,
        "balanced_runs_per_configuration": 9,
        "balanced_bootstrap_repetitions": 5000,
        "icc_bootstrap_repetitions": 1000,
    }


def run(output_dir: Path) -> dict[str, object]:
    evidence = validate_evidence()
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "acm_ieee_delta.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ROWS[0]))
        writer.writeheader()
        writer.writerows(ROWS)
    result = {
        "review_points": ["R1.8", "R2.5"],
        "published_article_doi": ACM_DOI,
        "comparison_rows": len(ROWS),
        "evidence": evidence,
        "novelty_exclusions": [
            "Lilith/Diablo/Kollaps framework",
            "released corpus and experimental design",
            "P0--P3 evidence ladder",
            "IQR%, Std%, and WCD definitions",
            "factorial ANOVA and ICC as previously reported",
            "previously published aggregate headlines",
        ],
    }
    (output_dir / "study_delta.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(json.dumps(run(args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
