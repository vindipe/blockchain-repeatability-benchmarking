from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.bootstrap_dispersion_tables import (
    DEFAULT_SEED,
    bootstrap_cell_dispersion,
    latex_estimate,
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

    def test_percentile_interval_outlier_receives_dagger(self) -> None:
        row = pd.Series(
            {"point_estimate": 12.93, "ci_lower": 6.73, "ci_upper": 12.82}
        )
        self.assertEqual(latex_estimate(row), r"12.93$^{\dagger}$ [6.73, 12.82]")

    def test_end_to_end_run_generates_combined_latex_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            summary = run_bootstrap(
                DATASET, output, repetitions=5, seed=DEFAULT_SEED
            )
            self.assertEqual(summary["method"]["interval"], "percentile")
            self.assertEqual(summary["method"]["repetitions"], 5)
            self.assertEqual(len(summary["generated_latex_tables"]), 6)

            table_path = (
                output
                / "six_workloads"
                / "table_topology.tex"
            )
            latex = table_path.read_text(encoding="utf-8")
            self.assertIn("Auto-generated", latex)
            self.assertIn(r"\begin{table*}[t]", latex)
            self.assertNotIn(r"\color{olive}", latex)
            self.assertEqual(latex.count(r"\vd["), 1)
            self.assertIn(r"\caption{\vd[R1.1-3-4-7]{", latex)
            self.assertNotIn("seed", latex.lower())
            self.assertIn(r"\TableFont", latex)
            self.assertNotIn(r"\footnotesize", latex)
            self.assertNotIn(r"\scriptsize", latex)
            self.assertIn(r"\setlength{\tabcolsep}{1.5pt}", latex)
            self.assertIn(r"\resizebox{\textwidth}{!}{%", latex)
            self.assertIn(r"\begin{tabular}{ll*{3}{rrrll}}", latex)
            self.assertIn(r"\makecell[l]", latex)
            self.assertNotIn(r"\makecell[r]", latex)
            self.assertNotIn(r"\adjustbox", latex)
            self.assertIn(r"\multicolumn{5}{c}{\textbf{TPS}}", latex)
            self.assertIn(r"\multicolumn{5}{c}{\textbf{Latency (s)}}", latex)
            self.assertIn(r"\multicolumn{5}{c}{\textbf{Energy (kWh)}}", latex)
            self.assertIn("Each metric block reports", latex)
            self.assertNotIn("Conventions are as in", latex)
            self.assertIn(r"$\mu$", latex)
            self.assertIn(r"$\widetilde{x}$", latex)
            self.assertGreater(latex.count(r"\bestline{"), 0)
            self.assertGreater(latex.count(r"\worstline{"), 0)
            self.assertNotIn("green and bold (best)", latex)
            self.assertNotIn("orange and italics (worst)", latex)
            self.assertIn(r"\label{tab:repeatability_topology}", latex)
            self.assertFalse(
                (output / "six_workloads" / "table_topology_tps.tex").exists()
            )
            legacy_latex = (
                output
                / "legacy_three_workloads"
                / "table_topology.tex"
            ).read_text(encoding="utf-8")
            self.assertIn(
                r"\label{tab:repeatability_topology}", legacy_latex
            )

            scaling_latex = (
                output / "six_workloads" / "table_scaling.tex"
            ).read_text(encoding="utf-8")
            workload_latex = (
                output / "six_workloads" / "table_workload.tex"
            ).read_text(encoding="utf-8")
            self.assertIn(
                r"Conventions are as in Table~\ref{tab:repeatability_topology}",
                workload_latex,
            )
            self.assertNotIn("Each metric block reports", workload_latex)
            self.assertIn(r"$^{\dagger}$", scaling_latex)
            self.assertIn("need not contain", scaling_latex)

            factor = pd.read_csv(output / "factor_bootstrap_summary.csv")
            defined = factor["contributing_configuration_cells"] > 0
            self.assertTrue(
                (factor.loc[defined, "ci_lower"] <= factor.loc[defined, "ci_upper"]).all()
            )


if __name__ == "__main__":
    unittest.main()
