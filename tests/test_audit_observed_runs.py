from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from analysis.audit_observed_runs import (
    normalise_labels,
    run_audit,
    select_controlled_corpus,
    validate_provenance,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ObservedRunAuditTests(unittest.TestCase):
    def test_released_dataset_matches_frozen_m1_inventory(self) -> None:
        summary = run_audit(
            REPOSITORY_ROOT / "dataset" / "reproducibility-runs.csv",
            output_dir=None,
        )

        self.assertEqual(summary["input"]["rows"], 4105)
        self.assertEqual(summary["input"]["columns"], 26)
        self.assertEqual(
            summary["input"]["sha256"],
            "c520ec25a02f2bc7e8c719c8b2dd0524c4c6a11d1d53953d77bb361d3f96b765",
        )

        selected = summary["selected_corpus"]
        self.assertEqual(selected["rows"], 4080)
        self.assertEqual(selected["configurations"], 300)
        self.assertEqual(selected["campaign_hashes"], 1006)
        self.assertEqual(selected["n_observed_min"], 9)
        self.assertEqual(selected["n_observed_max"], 26)
        self.assertEqual(selected["n_observed_distribution"]["10"], 4)
        self.assertEqual(selected["run_values"], list(range(1, 11)))

        legacy = summary["legacy_three_workload_subset"]
        self.assertEqual(legacy["rows"], 2053)
        self.assertEqual(legacy["configurations"], 150)
        self.assertEqual(legacy["n_observed_min"], 9)
        self.assertEqual(legacy["n_observed_max"], 26)
        self.assertEqual(legacy["n_observed_distribution"]["10"], 2)

    def test_fixed_filters_are_applied_after_label_normalisation(self) -> None:
        raw = pd.DataFrame(
            [
                {
                    "hash": "a",
                    "run": 1,
                    "start_bench": "2024-01-01",
                    "blockchain": "poa",
                    "mode": "full-mesh-l",
                    "workload": "paypal",
                    "cores": 8,
                    "ram": 16,
                    "secondaries": 10,
                    "dataset": "diablo",
                    "link_strategy": "hop",
                    "network_size": 1,
                    "dynamic": 0,
                },
                {
                    "hash": "b",
                    "run": 1,
                    "start_bench": "2024-01-01",
                    "blockchain": "poa",
                    "mode": "full-mesh-l",
                    "workload": "paypal",
                    "cores": 4,
                    "ram": 16,
                    "secondaries": 10,
                    "dataset": "diablo",
                    "link_strategy": "hop",
                    "network_size": 1,
                    "dynamic": 0,
                },
            ]
        )
        selected = select_controlled_corpus(normalise_labels(raw))
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected.iloc[0]["blockchain"], "Ethereum")
        self.assertEqual(selected.iloc[0]["mode"], "full mesh")
        self.assertEqual(selected.iloc[0]["workload"], "PayPal")
        self.assertEqual(selected.iloc[0]["network_size"], "10 nodes")

    def test_duplicate_provenance_pair_is_rejected(self) -> None:
        row = {
            "hash": "a",
            "run": 1,
            "start_bench": "2024-01-01",
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
        }
        with self.assertRaisesRegex(ValueError, r"Duplicate \(hash, run\)"):
            validate_provenance(pd.DataFrame([row, row]))

    def test_campaign_crossing_configurations_is_rejected(self) -> None:
        first = {
            "hash": "a",
            "run": 1,
            "start_bench": "2024-01-01",
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
        }
        second = {**first, "run": 2, "blockchain": "Diem"}
        with self.assertRaisesRegex(ValueError, "spanning multiple configurations"):
            validate_provenance(pd.DataFrame([first, second]))


if __name__ == "__main__":
    unittest.main()
