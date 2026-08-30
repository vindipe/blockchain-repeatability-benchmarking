from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from analysis.audit_observed_runs import CONFIGURATION_COLUMNS, load_runs
from analysis.derive_run_outcomes import (
    configuration_outcome_counts,
    derive_outcomes,
    prepare_selected_runs,
    run_derivation,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPOSITORY_ROOT / "dataset" / "reproducibility-runs.csv"


def synthetic_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "hash": "abc123",
        "run": 1,
        "start_bench": "2024-01-01 00:00:00",
        "blockchain": "Algorand",
        "mode": "torus",
        "workload": "VISA",
        "cores": 8,
        "ram": 16,
        "secondaries": 10,
        "dataset": "2023",
        "link_strategy": "hop",
        "network_size": "10 nodes",
        "dynamic": 0,
        "submit_number": 100,
        "commit_number": 90,
        "average_throughput": 1.0,
        "average_latency": 2.0,
        "median_latency": 2.0,
        "energy": 3.0,
        "MiB-Rx": 4.0,
        "MiB-Tx": 5.0,
    }
    row.update(overrides)
    return row


class RunOutcomeDerivationTests(unittest.TestCase):
    def test_released_dataset_outcome_counts(self) -> None:
        summary = run_derivation(DATASET, output_dir=None)
        full = summary["selected_six_workload_corpus"]
        self.assertEqual(
            full["outcome_counts"],
            {
                "positive_commit": 3125,
                "zero_commit": 953,
                "no_submission": 2,
                "inconsistent": 0,
            },
        )
        self.assertEqual(
            full["configuration_regimes"],
            {
                "all_positive_commit": 205,
                "mixed_outcomes": 46,
                "no_positive_commit": 49,
            },
        )
        self.assertEqual(
            full["configurations_with_at_least_9_positive_commits"], 231
        )

        legacy = summary["legacy_three_workload_subset"]
        self.assertEqual(
            legacy["outcome_counts"],
            {
                "positive_commit": 1770,
                "zero_commit": 283,
                "no_submission": 0,
                "inconsistent": 0,
            },
        )
        self.assertEqual(
            legacy["configurations_with_at_least_9_positive_commits"], 129
        )

    def test_metric_specific_released_counts(self) -> None:
        summary = run_derivation(DATASET, output_dir=None)
        full = summary["selected_six_workload_corpus"]
        self.assertEqual(
            full["metric_valid_counts"],
            {
                "tps_valid_positive_commit": 3125,
                "tps_censored_positive_commit": 7,
                "tps_point_valid_positive_commit": 3118,
                "latency_valid_positive_commit": 3125,
                "energy_valid_observed": 4080,
                "energy_valid_positive_commit": 3125,
                "network_valid_observed": 4080,
            },
        )
        self.assertEqual(full["positive_commit_with_stored_tps_zero"], 7)

    def test_positive_commit_with_rounded_zero_tps_is_censored(self) -> None:
        row = synthetic_row(commit_number=1, average_throughput=0.0)
        derived = derive_outcomes(pd.DataFrame([row])).iloc[0]
        self.assertEqual(derived["outcome_status_derived"], "positive_commit")
        self.assertTrue(derived["tps_valid_positive_commit"])
        self.assertTrue(derived["tps_censored_positive_commit"])
        self.assertFalse(derived["tps_point_valid_positive_commit"])
        self.assertTrue(derived["latency_valid_positive_commit"])

    def test_zero_commit_keeps_energy_and_network_but_not_performance(self) -> None:
        row = synthetic_row(
            commit_number=0,
            average_throughput=0.0,
            average_latency=0.0,
            median_latency=0.0,
        )
        derived = derive_outcomes(pd.DataFrame([row])).iloc[0]
        self.assertEqual(derived["outcome_status_derived"], "zero_commit")
        self.assertFalse(derived["tps_valid_positive_commit"])
        self.assertFalse(derived["latency_valid_positive_commit"])
        self.assertTrue(derived["energy_valid_observed"])
        self.assertFalse(derived["energy_valid_positive_commit"])
        self.assertTrue(derived["network_valid_observed"])

    def test_no_submission_is_distinct_from_zero_commit(self) -> None:
        row = synthetic_row(
            submit_number=0,
            commit_number=0,
            average_throughput=0.0,
            average_latency=0.0,
        )
        derived = derive_outcomes(pd.DataFrame([row])).iloc[0]
        self.assertEqual(derived["outcome_status_derived"], "no_submission")
        self.assertFalse(derived["submitted_derived"])
        self.assertTrue(derived["energy_valid_observed"])

    def test_contradictory_transaction_counts_are_inconsistent(self) -> None:
        row = synthetic_row(submit_number=10, commit_number=11)
        derived = derive_outcomes(pd.DataFrame([row])).iloc[0]
        self.assertEqual(derived["outcome_status_derived"], "inconsistent")
        self.assertTrue(derived["inconsistent_derived"])

    def test_non_integral_large_transaction_count_is_inconsistent(self) -> None:
        row = synthetic_row(submit_number=540000.1, commit_number=10)
        derived = derive_outcomes(pd.DataFrame([row])).iloc[0]
        self.assertEqual(derived["outcome_status_derived"], "inconsistent")
        self.assertTrue(derived["inconsistent_derived"])

    def test_configuration_counts_are_exhaustive(self) -> None:
        raw = load_runs(DATASET)
        derived = derive_outcomes(prepare_selected_runs(raw))
        counts = configuration_outcome_counts(derived)
        self.assertEqual(len(counts), 300)
        self.assertTrue(
            (
                counts["n_positive_commit"]
                + counts["n_zero_commit"]
                + counts["n_no_submission"]
                + counts["n_inconsistent"]
                == counts["n_observed"]
            ).all()
        )
        self.assertEqual(list(counts.columns[: len(CONFIGURATION_COLUMNS)]), CONFIGURATION_COLUMNS)


if __name__ == "__main__":
    unittest.main()
