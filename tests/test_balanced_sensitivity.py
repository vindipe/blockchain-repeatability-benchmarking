from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from analysis.audit_observed_runs import load_runs
from analysis.balanced_sensitivity import (
    BALANCED_SAMPLE_SIZE,
    DEFAULT_SEED,
    draw_balanced_indices,
    prepare_configuration_cells,
    run_sensitivity,
)
from analysis.derive_run_outcomes import derive_outcomes, prepare_selected_runs


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPOSITORY_ROOT / "dataset" / "reproducibility-runs.csv"


class BalancedSensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.derived = derive_outcomes(prepare_selected_runs(load_runs(DATASET))).reset_index(
            drop=True
        )
        cls.configurations, cls.cells = prepare_configuration_cells(cls.derived)

    def test_every_configuration_supports_balanced_nine(self) -> None:
        self.assertEqual(len(self.configurations), 300)
        self.assertEqual(int(self.configurations["n_observed"].min()), 9)
        self.assertEqual(int(self.configurations["n_observed"].max()), 26)

    def test_draws_are_real_unique_rows_within_each_cell(self) -> None:
        draws = draw_balanced_indices(self.cells, repetitions=12, seed=DEFAULT_SEED)
        for source, sampled in zip(self.cells, draws, strict=True):
            self.assertEqual(sampled.shape, (12, BALANCED_SAMPLE_SIZE))
            for repetition in sampled:
                self.assertEqual(len(np.unique(repetition)), BALANCED_SAMPLE_SIZE)
                self.assertTrue(np.isin(repetition, source).all())

    def test_seed_is_reproducible(self) -> None:
        first = draw_balanced_indices(self.cells, repetitions=3, seed=73)
        second = draw_balanced_indices(self.cells, repetitions=3, seed=73)
        for left, right in zip(first, second, strict=True):
            np.testing.assert_array_equal(left, right)

    def test_small_end_to_end_run_writes_expected_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            summary = run_sensitivity(
                DATASET, output, repetitions=5, seed=DEFAULT_SEED
            )
            self.assertEqual(summary["method"]["sample_size_per_configuration"], 9)
            self.assertEqual(summary["method"]["synthetic_rows"], 0)
            self.assertEqual(summary["selected_configurations"], 300)
            for filename in (
                "balanced_sensitivity_summary.json",
                "configuration_sensitivity.csv",
                "denominator_sensitivity.csv",
                "extrema_sensitivity.csv",
                "factor_sensitivity.csv",
            ):
                self.assertTrue((output / filename).is_file(), filename)


if __name__ == "__main__":
    unittest.main()
