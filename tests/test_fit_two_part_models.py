import unittest

import pandas as pd

from analysis.audit_observed_runs import DEFAULT_INPUT, PRIMARY_WORKLOADS_LEGACY, load_runs
from analysis.derive_run_outcomes import derive_outcomes, prepare_selected_runs
from analysis.fit_two_part_models import (
    METRIC_SPECS,
    fit_binomial,
    fit_linear_metric,
    render_three_way_sensitivity_table,
    render_term_table,
    targeted_three_way_sensitivity,
    three_way_estimability,
)


class TwoPartModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        derived = derive_outcomes(prepare_selected_runs(load_runs(DEFAULT_INPUT)))
        cls.legacy = derived.loc[
            derived["workload"].isin(PRIMARY_WORKLOADS_LEGACY)
        ].copy()

    def test_legacy_models_are_full_rank(self):
        _, _, outcome_diagnostics = fit_binomial(self.legacy)
        self.assertTrue(outcome_diagnostics["full_rank"])
        for metric in METRIC_SPECS:
            _, _, _, diagnostics = fit_linear_metric(self.legacy, metric)
            self.assertTrue(diagnostics["full_rank"])

    def test_legacy_targeted_three_way_terms_are_estimable(self):
        for metric in METRIC_SPECS:
            table = three_way_estimability(self.legacy, metric)
            self.assertTrue(table["fully_estimable"].all())

    def test_generated_table_has_stable_label(self):
        _, outcome, _ = fit_binomial(self.legacy)
        parts = []
        for metric in METRIC_SPECS:
            _, primary, _, diagnostics = fit_linear_metric(self.legacy, metric)
            primary.insert(0, "metric", metric)
            primary["design_full_rank"] = bool(diagnostics["full_rank"])
            parts.append(primary)
        latex = render_term_table(outcome, pd.concat(parts, ignore_index=True))
        self.assertIn(r"\label{tab:two_part_factorial_models}", latex)
        self.assertIn(r"\resizebox{\textwidth}{!}", latex)
        self.assertIn("hierarchical omnibus", latex)
        self.assertNotIn("rank-deficient", latex)

    def test_rank_deficient_metric_is_suppressed_in_latex_table(self):
        _, outcome, _ = fit_binomial(self.legacy)
        parts = []
        for metric in METRIC_SPECS:
            _, primary, _, diagnostics = fit_linear_metric(self.legacy, metric)
            primary.insert(0, "metric", metric)
            primary["design_full_rank"] = bool(diagnostics["full_rank"])
            if metric == "TPS":
                primary["design_full_rank"] = False
            parts.append(primary)
        latex = render_term_table(outcome, pd.concat(parts, ignore_index=True))
        self.assertIn("-- & -- & --", latex)
        self.assertIn("rank-deficient", latex)

    def test_legacy_targeted_three_way_sensitivity_is_reported(self):
        table = targeted_three_way_sensitivity(self.legacy)
        self.assertEqual(len(table), 8)
        self.assertTrue(table["fully_estimable"].all())
        latex = render_three_way_sensitivity_table(table)
        self.assertIn(r"\label{tab:three_way_sensitivity}", latex)
        self.assertIn("likelihood-ratio", latex)
        self.assertIn("HC3 Type-II", latex)


if __name__ == "__main__":
    unittest.main()
