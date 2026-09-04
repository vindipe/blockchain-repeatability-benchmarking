import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from analysis.icc_by_blockchain import (
    cluster_bootstrap,
    fit_random_intercept,
    render_icc_table,
    render_tables_from_results,
)


class ICCModelTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(17)
        group_effects = rng.normal(0, 1.0, size=12)
        self.groups = np.repeat(np.arange(12), 8)
        self.values = group_effects[self.groups] + rng.normal(0, 0.4, size=96)

    def test_random_intercept_components_and_icc_are_valid(self):
        result = fit_random_intercept(self.values, self.groups)
        self.assertTrue(result["converged"])
        self.assertGreaterEqual(result["icc"], 0)
        self.assertLessEqual(result["icc"], 1)
        self.assertGreater(result["between_configuration_variance"], 0)
        self.assertGreater(result["within_configuration_variance"], 0)

    def test_cluster_bootstrap_is_seed_reproducible(self):
        first, failures_first = cluster_bootstrap(
            self.values, self.groups, repetitions=5, seed=99
        )
        second, failures_second = cluster_bootstrap(
            self.values, self.groups, repetitions=5, seed=99
        )
        np.testing.assert_allclose(first, second)
        self.assertEqual(failures_first, failures_second)

    def test_generated_table_uses_fixed_table_font(self):
        table = pd.DataFrame(
            [
                {
                    "blockchain": "Algorand",
                    "metric": metric,
                    "icc": 0.5,
                    "ci_lower": 0.4,
                    "ci_upper": 0.6,
                }
                for metric in ("TPS", "Latency", "Energy")
            ]
        )
        latex = render_icc_table(table, repetitions=10)
        self.assertIn(r"\setlength{\tabcolsep}{1pt}", latex)
        self.assertIn(r"\begin{tabular}{lrrr}", latex)
        self.assertIn(r"\resizebox{\columnwidth}{!}{%", latex)
        self.assertIn(r"\begin{table}[t]", latex)
        self.assertNotIn(r"\color{olive}", latex)
        self.assertEqual(latex.count(r"\vd{"), 1)
        self.assertIn(r"\caption{\vd{R2.4:", latex)
        self.assertIn(r"\TableFont", latex)
        self.assertNotIn("seed", latex.lower())

    def test_tables_can_be_rebuilt_from_completed_results(self):
        rows = []
        for scope, seed in (
            ("legacy_three_workloads", 1),
            ("six_workloads", 4),
        ):
            for metric in ("TPS", "Latency", "Energy"):
                rows.append(
                    {
                        "scope": scope,
                        "blockchain": "Algorand",
                        "metric": metric,
                        "icc": 0.5,
                        "ci_lower": 0.4,
                        "ci_upper": 0.6,
                        "bootstrap_repetitions": 10,
                        "seed": seed,
                    }
                )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pd.DataFrame(rows).to_csv(root / "icc_by_blockchain.csv", index=False)
            summary = render_tables_from_results(root, root / "tables")
            self.assertEqual(summary["scopes"]["six_workloads"]["first_seed"], 4)
            self.assertTrue(
                (root / "tables" / "legacy_three_workloads"
                 / "table_icc_by_blockchain.tex").exists()
            )


if __name__ == "__main__":
    unittest.main()
