"""Run the complete IEEE Access revision workflow and record a frozen manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "outputs/revision/clean_room_manifest.json"


def workflow_commands(icc_workers: int | None = None) -> list[list[str]]:
    python = sys.executable
    commands = [
        [python, "analysis/audit_observed_runs.py"],
        [python, "analysis/audit_topology_instances.py"],
        [python, "analysis/derive_run_outcomes.py"],
        [python, "analysis/compute_corrected_dispersion.py"],
        [python, "analysis/balanced_sensitivity.py"],
        [python, "analysis/bootstrap_dispersion_tables.py"],
        [python, "analysis/fit_two_part_models.py"],
    ]
    icc = [python, "analysis/icc_by_blockchain.py"]
    if icc_workers is not None:
        icc.extend(["--workers", str(icc_workers)])
    commands.extend(
        [
            icc,
            [python, "analysis/audit_gafam_trace.py"],
            [python, "analysis/workload_catalog.py"],
            [python, "analysis/plot_run_level_deviations.py"],
            [python, "analysis/audit_campaign_structure.py"],
            [python, "analysis/generate_study_delta.py"],
            [python, "-m", "unittest", "discover", "-s", "tests", "-v"],
        ]
    )
    return commands


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frozen_output_hashes() -> dict[str, str]:
    roots = [REPOSITORY_ROOT / "outputs/revision", REPOSITORY_ROOT / "paper_tables"]
    hashes: dict[str, str] = {}
    for root in roots:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            if path == MANIFEST_PATH:
                continue
            hashes[str(path.relative_to(REPOSITORY_ROOT))] = sha256(path)
    return hashes


def read_json(path: str) -> dict[str, object]:
    return json.loads((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


def validate_frozen_results() -> dict[str, object]:
    outcomes = read_json("outputs/revision/m2_outcomes/outcome_summary.json")
    workloads = read_json("outputs/revision/m1_workloads/summary.json")
    balanced = read_json("outputs/revision/balanced_n9/balanced_sensitivity_summary.json")
    bootstrap = read_json("outputs/revision/m4_bootstrap/bootstrap_summary.json")
    icc = read_json("outputs/revision/icc_by_blockchain/summary.json")
    campaign = read_json("outputs/revision/m6_campaign_structure/campaign_identifier_audit.json")
    delta = read_json("outputs/revision/m8_study_delta/study_delta.json")
    figures = read_json("outputs/revision/m1_figures/summary.json")

    expected = {
        "observed_executions": 4080,
        "configuration_cells": 300,
        "workloads": 6,
        "positive_commit": 3125,
        "zero_commit": 953,
        "no_submission": 2,
    }
    observed = {
        "observed_executions": workloads.get("observed_executions"),
        "configuration_cells": workloads.get("configuration_cells"),
        "workloads": workloads.get("workloads"),
        "positive_commit": workloads.get("positive_commit"),
        "zero_commit": workloads.get("zero_commit"),
        "no_submission": workloads.get("no_submission"),
    }
    if observed != expected:
        raise ValueError(f"Frozen corpus totals changed: {observed}")
    checks = {
        **observed,
        "inconsistent": outcomes.get("selected_six_workload_corpus", {})
        .get("outcome_counts", {})
        .get("inconsistent"),
        "balanced_repetitions": balanced.get("method", {}).get("repetitions"),
        "dispersion_bootstrap_repetitions": bootstrap.get("method", {}).get("repetitions"),
        "icc_models": icc.get("models"),
        "icc_repetitions": icc.get("repetitions"),
        "icc_bootstrap_failures": icc.get("bootstrap_failures"),
        "hash_batches": campaign.get("hash_batches"),
        "delta_rows": delta.get("comparison_rows"),
        "figure_pdfs": figures.get("pdf_count"),
        "outcome_figure_configurations": figures.get("configuration_outcome_rows"),
        "plotted_execution_rows": figures.get("manifest_rows"),
    }
    required = {
        "inconsistent": 0,
        "balanced_repetitions": 5000,
        "dispersion_bootstrap_repetitions": 5000,
        "icc_models": 30,
        "icc_repetitions": 1000,
        "icc_bootstrap_failures": 0,
        "hash_batches": 1006,
        "delta_rows": 7,
        "figure_pdfs": 13,
        "outcome_figure_configurations": 300,
        "plotted_execution_rows": 9368,
    }
    for key, value in required.items():
        if checks[key] != value:
            raise ValueError(f"Frozen result check failed for {key}: {checks[key]}")
    return checks


def run_workflow(icc_workers: int | None = None) -> dict[str, object]:
    steps = []
    started = time.time()
    for command in workflow_commands(icc_workers):
        step_started = time.time()
        print(f"[revision] running: {' '.join(command)}", flush=True)
        completed = subprocess.run(command, cwd=REPOSITORY_ROOT, check=False)
        elapsed = time.time() - step_started
        steps.append(
            {
                "command": command,
                "elapsed_seconds": round(elapsed, 3),
                "return_code": completed.returncode,
            }
        )
        if completed.returncode != 0:
            raise subprocess.CalledProcessError(completed.returncode, command)

    result_checks = validate_frozen_results()
    manifest = {
        "workflow": "complete IEEE Access revision analysis",
        "python": sys.version,
        "platform": platform.platform(),
        "requirements_sha256": sha256(REPOSITORY_ROOT / "requirements.txt"),
        "dataset_sha256": sha256(REPOSITORY_ROOT / "dataset/reproducibility-runs.csv"),
        "total_elapsed_seconds": round(time.time() - started, 3),
        "steps": steps,
        "result_checks": result_checks,
        "output_sha256": frozen_output_hashes(),
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--icc-workers",
        type=int,
        default=None,
        help="Explicit worker count for the full 1,000-repetition ICC bootstrap.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    run_workflow(args.icc_workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
