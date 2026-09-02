from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.bootstrap_dispersion_tables import (
    DEFAULT_SEED,
    bootstrap_cell_dispersion,
    run_bootstrap,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET = REPOSITORY_ROOT / "dataset" / "reproducibility-runs.csv"


class BootstrapDispersionTableTests(unittest.TestCase):
    def test_cell_bootstrap_is_seed_reproducible(self) -> None:
        values = np.asarray([1.0, 2.0, 4.0, 8.0])
        first = bootstrap_cell_dispersion(
            values, 20, np.random.default_rng(DEFAULT_SEED)
        )
        second = bootstrap_cell_dispersion(
            values, 20, np.random.default_rng(DEFAULT_SEED)
        )
        for statistic in ("iqr_pct", "sample_std_pct"):
            np.testing.assert_array_equal(first[statistic], second[statistic])
            self.assertTrue(np.isfinite(first[statistic]).all())

    def test_single_observation_has_no_dispersion_interval(self) -> None:
        result = bootstrap_cell_dispersion(
            np.asarray([4.0]), 10, np.random.default_rng(DEFAULT_SEED)
        )
        self.assertTrue(np.isnan(result["iqr_pct"]).all())
        self.assertTrue(np.isnan(result["sample_std_pct"]).all())

    def test_end_to_end_run_generates_independent_latex_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            summary = run_bootstrap(
                DATASET, output, repetitions=5, seed=DEFAULT_SEED
            )
            self.assertEqual(summary["method"]["interval"], "percentile")
            self.assertEqual(summary["method"]["repetitions"], 5)
            self.assertEqual(len(summary["generated_latex_tables"]), 18)

            table_path = (
                output
                / "six_workloads"
                / "table_topology_tps.tex"
            )
            latex = table_path.read_text(encoding="utf-8")
            self.assertIn("Auto-generated", latex)
            self.assertIn(r"\begin{table*}[t]", latex)
            self.assertNotIn(r"\color{olive}", latex)
            self.assertEqual(latex.count(r"\vd{"), 1)
            self.assertIn(r"\caption{\vd{R1.1-3-4-7:", latex)
            self.assertIn(r"\TableFont", latex)
            self.assertNotIn(r"\footnotesize", latex)
            self.assertNotIn(r"\scriptsize", latex)
            self.assertIn(r"\setlength{\tabcolsep}{2pt}", latex)
            self.assertNotIn(r"\adjustbox", latex)
            self.assertGreater(latex.count(r"\hlcell{best}"), 0)
            self.assertGreater(latex.count(r"\hlcell{worst}"), 0)
            self.assertNotIn("green and bold (best)", latex)
            self.assertNotIn("orange and italics (worst)", latex)
            self.assertIn(r"\label{tab:repeatability_topology_tps}", latex)
            legacy_latex = (
                output
                / "legacy_three_workloads"
                / "table_topology_tps.tex"
            ).read_text(encoding="utf-8")
            self.assertIn(
                r"\label{tab:repeatability_topology_tps}", legacy_latex
            )

            factor = pd.read_csv(output / "factor_bootstrap_summary.csv")
            defined = factor["contributing_configuration_cells"] > 0
            self.assertTrue(
                (factor.loc[defined, "ci_lower"] <= factor.loc[defined, "ci_upper"]).all()
            )


if __name__ == "__main__":
    unittest.main()
