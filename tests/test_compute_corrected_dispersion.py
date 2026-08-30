from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.compute_corrected_dispersion import (
    compute_configuration_table,
    configuration_statistics,
    run_analysis,
)
from analysis.audit_observed_runs import load_runs
from analysis.derive_run_outcomes import derive_outcomes, prepare_selected_runs


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPOSITORY_ROOT / "dataset" / "reproducibility-runs.csv"


class CorrectedDispersionTests(unittest.TestCase):
    def test_known_sample_standard_deviation_uses_ddof_one(self) -> None:
        values = pd.Series([1.0, 2.0, 3.0])
        stats = configuration_statistics(values)
        self.assertAlmostEqual(stats["sample_std"], 1.0)
        self.assertAlmostEqual(stats["sample_std"], values.std(ddof=1))

    def test_directional_deviations_use_the_same_values(self) -> None:
        stats = configuration_statistics(pd.Series([0.0, 0.0, 3.0]))
        self.assertEqual(stats["mean"], 1.0)
        self.assertEqual(stats["delta_min_pct"], -100.0)
        self.assertEqual(stats["delta_max_pct"], 200.0)
        self.assertEqual(stats["range_abs"], 3.0)

    def test_upward_bound_is_reached_for_one_positive_value(self) -> None:
        n = 13
        stats = configuration_statistics(pd.Series([0.0] * (n - 1) + [1.0]))
        self.assertAlmostEqual(stats["delta_max_pct"], 100.0 * (n - 1))

    def test_released_analysis_has_no_1200_percent_conditional_tps_tail(self) -> None:
        summary = run_analysis(DATASET, output_dir=None)
        full = summary["selected_six_workload_corpus"]
        tps = full["tps_positive_commit"]
        self.assertEqual(tps["metric_observations"], 3118)
        self.assertLess(tps["maxima"]["delta_max_pct"]["value"], 1200.0)
        self.assertEqual(
            summary["method"]["tps_rounding"]["positive_commit_left_censored_rows"],
            7,
        )

    def test_reviewed_one_positive_twelve_zero_cell_has_one_tps_value(self) -> None:
        derived = derive_outcomes(prepare_selected_runs(load_runs(DATASET)))
        table = compute_configuration_table(derived)
        row = table.loc[
            (table["blockchain"] == "Solana")
            & (table["mode"] == "hypercube")
            & (table["workload"] == "PayPal")
            & (table["network_size"] == "40 nodes")
            & (table["metric"] == "tps_positive_commit")
        ].iloc[0]
        self.assertEqual(row["n_observed"], 13)
        self.assertEqual(row["n_positive_commit"], 1)
        self.assertEqual(row["n_zero_commit"], 12)
        self.assertEqual(row["n_metric"], 1)
        self.assertEqual(row["delta_max_pct"], 0.0)
        self.assertTrue(np.isnan(row["sample_std"]))

    def test_singleton_standard_deviation_is_undefined(self) -> None:
        stats = configuration_statistics(pd.Series([4.0]))
        self.assertTrue(np.isnan(stats["sample_std"]))
        self.assertTrue(np.isnan(stats["sample_std_pct"]))


if __name__ == "__main__":
    unittest.main()
