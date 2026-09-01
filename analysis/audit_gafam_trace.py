"""Audit the GAFAM trace definition and its link to the released corpus (R1.13)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

try:
    from .audit_observed_runs import (
        DEFAULT_INPUT,
        load_runs,
        normalise_labels,
        select_controlled_corpus,
    )
except ImportError:  # Direct execution
    from audit_observed_runs import (  # type: ignore[no-redef]
        DEFAULT_INPUT,
        load_runs,
        normalise_labels,
        select_controlled_corpus,
    )


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACE = REPOSITORY_ROOT / "inputs" / "workloads" / "workload-gafam-long.yaml"
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "m2_gafam_trace"
EXPECTED_TRACE_SHA256 = "11d4fb66ef30608764bb91ee8fb62ecddc294c6d19fc2d8ba7cd9e71d7ce83b7"
UPSTREAM_TRACE_SHA256 = "11fd627b4fba15884605b1fda1e11d701b10538b9f1ccf9e61fd458e2aff17ba"
SOURCE_REPOSITORY = "https://github.com/vindipe/lilith"
SOURCE_COMMIT = "dd1d457c6079661b158f601cdf70817cbe2a5f2a"
SOURCE_PATH = "kollaps/examples/diablo/primary/fixes/workload-gafam-long.yaml"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_trace(path: Path) -> tuple[str, str, dict[int, int]]:
    text = path.read_text(encoding="utf-8")
    identifier = re.search(r'^id:\s*"([^"]+)"\s*$', text, re.MULTILINE)
    contract = re.search(r'^contract:\s*"([^"]+)"\s*$', text, re.MULTILINE)
    if identifier is None or contract is None:
        raise ValueError("Trace must define quoted id and contract fields")

    schedule: dict[int, int] = {}
    in_schedule = False
    for line in text.splitlines():
        if line.strip() == "txs:":
            in_schedule = True
            continue
        if not in_schedule or not line.strip():
            continue
        match = re.fullmatch(r"\s+(\d+):\s+(\d+)\s*", line)
        if match is None:
            raise ValueError(f"Invalid txs schedule line: {line!r}")
        schedule[int(match.group(1))] = int(match.group(2))
    if not schedule:
        raise ValueError("Trace contains no txs schedule")
    return identifier.group(1), contract.group(1), schedule


def validate_trace(identifier: str, contract: str, schedule: dict[int, int]) -> None:
    if identifier != "smart-gafam":
        raise ValueError(f"Unexpected trace id: {identifier}")
    if contract != "gafam:buy":
        raise ValueError(f"Unexpected contract selector: {contract}")
    if schedule.get(0) != 19_800:
        raise ValueError("GAFAM trace must start at the 19,800-TPS control point")
    if schedule.get(1) != 115:
        raise ValueError("GAFAM trace must contain the 115-TPS control point at t=1")
    if max(schedule) != 300 or schedule[300] != 0:
        raise ValueError("GAFAM trace must terminate at t=300 with zero offered TPS")
    post_burst = [rate for second, rate in schedule.items() if 1 <= second <= 180]
    if min(post_burst) != 25 or max(post_burst) != 140:
        raise ValueError("Post-burst control points through t=180 must span 25--140 TPS")


def corpus_audit(input_path: Path) -> dict[str, object]:
    raw = load_runs(input_path)
    raw_gafam = raw.loc[(raw["dataset"] == "diablo") & (raw["workload"] == "gafam")]
    selected = select_controlled_corpus(normalise_labels(raw))
    gafam = selected.loc[selected["workload"] == "GAFAM"]
    if len(gafam) != 668 or len(raw_gafam) != 668:
        raise ValueError("Expected 668 selected rows linked by gafam -> GAFAM")
    if sorted(gafam["submit_number"].dropna().unique().tolist()) != [30320]:
        raise ValueError("Unexpected submitted-transaction count for GAFAM rows")
    loads = sorted(float(value) for value in gafam["average_load"].dropna().unique())
    if loads != [167.6, 167.7]:
        raise ValueError(f"Unexpected recorded GAFAM average-load values: {loads}")
    return {
        "raw_workload_label": "gafam",
        "display_workload_label": "GAFAM",
        "selected_observations": int(len(gafam)),
        "submitted_transactions_per_observation": 30320,
        "recorded_average_load_tps": loads,
    }


def run(input_path: Path, trace_path: Path, output_dir: Path) -> dict[str, object]:
    digest = sha256_file(trace_path)
    if digest != EXPECTED_TRACE_SHA256:
        raise ValueError(f"Unexpected GAFAM trace SHA-256: {digest}")
    identifier, contract, schedule = parse_trace(trace_path)
    validate_trace(identifier, contract, schedule)
    corpus = corpus_audit(input_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"second": second, "offered_tps_control_point": rate} for second, rate in sorted(schedule.items())]
    ).to_csv(output_dir / "gafam_trace_schedule.csv", index=False)
    summary: dict[str, object] = {
        "review_point": "R1.13",
        "trace_filename": trace_path.name,
        "trace_sha256": digest,
        "upstream_trace_sha256": UPSTREAM_TRACE_SHA256,
        "mirror_normalization": "one terminating LF added; YAML content unchanged",
        "trace_duration_seconds": max(schedule),
        "time_unit": "seconds",
        "load_unit": "transactions per second (TPS)",
        "interpolation": "linear between control points (Diablo)",
        "trace_id": identifier,
        "contract": contract,
        "initial_control_point_tps": schedule[0],
        "control_point_at_second_1_tps": schedule[1],
        "post_burst_control_point_range_tps_through_second_180": [25, 140],
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": SOURCE_COMMIT,
        "source_path": SOURCE_PATH,
        "corpus_link": corpus,
    }
    (output_dir / "gafam_trace_audit.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    print(json.dumps(run(args.input, args.trace, args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
