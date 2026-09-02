import unittest

import pandas as pd

from analysis.audit_observed_runs import DEFAULT_INPUT, PRIMARY_WORKLOADS_LEGACY, load_runs
from analysis.derive_run_outcomes import derive_outcomes, prepare_selected_runs
from analysis.fit_two_part_models import (
    METRIC_SPECS,
    fit_binomial,
    fit_linear_metric,
    render_estimability_table,
    render_three_way_sensitivity_table,
    render_term_table,
    targeted_three_way_sensitivity,
    three_way_estimability,
)


class TwoPartModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        derived = derive_outcomes(prepare_selected_runs(load_runs(DEFAULT_INPUT)))
        cls.six = derived.copy()
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
        self.assertIn(r"\setlength{\tabcolsep}{2pt}", latex)
        self.assertNotIn(r"\resizebox", latex)
        self.assertNotIn(r"\color{olive}", latex)
        self.assertIn(r"\caption{\vd{R1.9-10:", latex)
        self.assertIn(r"\TableFont", latex)
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
        latex = render_three_way_sensitivity_table(
            table, outcome_quasi_separation=True
        )
        self.assertIn(r"\label{tab:three_way_sensitivity}", latex)
        self.assertIn(r"\setlength{\tabcolsep}{2pt}", latex)
        self.assertNotIn(r"\resizebox", latex)
        self.assertNotIn(r"\color{olive}", latex)
        self.assertIn(r"\caption{\vd{R1.11:", latex)
        self.assertIn("likelihood-ratio", latex)
        self.assertIn("HC3 Type-II", latex)
        self.assertIn("quasi-separation", latex)

        estimability_latex = render_estimability_table(
            three_way_estimability(self.legacy, "TPS")
        )
        self.assertNotIn(r"\color{olive}", estimability_latex)
        self.assertIn(r"\caption{\vd{R1.11:", estimability_latex)
        self.assertIn(r"\begin{table*}[t]", estimability_latex)

    def test_quasi_separation_is_disclosed_in_the_primary_table(self):
        _, outcome, _ = fit_binomial(self.legacy)
        parts = []
        for metric in METRIC_SPECS:
            _, primary, _, diagnostics = fit_linear_metric(self.legacy, metric)
            primary.insert(0, "metric", metric)
            primary["design_full_rank"] = bool(diagnostics["full_rank"])
            parts.append(primary)
        latex = render_term_table(
            outcome,
            pd.concat(parts, ignore_index=True),
            outcome_quasi_separation=True,
        )
        self.assertIn("quasi-separation", latex)

    def test_six_workload_models_use_full_rank_observed_support(self):
        for metric in METRIC_SPECS:
            _, primary, _, diagnostics = fit_linear_metric(self.six, metric)
            self.assertTrue(diagnostics["full_rank"])
            self.assertTrue(diagnostics["support_adjusted"])
            self.assertEqual(diagnostics["candidate_rank_deficiency"], 2)
            self.assertEqual(
                diagnostics["empty_positive_service_blockchain_workload_cells"],
                ["Quorum / FIFA", "Quorum / Gaming"],
            )
            interaction = primary.loc[
                primary["term_formula"].str.contains(
                    "C\\(blockchain, Sum\\):C\\(workload, Sum\\)", regex=True
                )
            ].iloc[0]
            self.assertEqual(interaction["df"], 18)
            self.assertEqual(interaction["nominal_df"], 20)

    def test_six_workload_table_reports_supported_inference(self):
        _, outcome, _ = fit_binomial(self.six)
        parts = []
        for metric in METRIC_SPECS:
            _, primary, _, diagnostics = fit_linear_metric(self.six, metric)
            primary.insert(0, "metric", metric)
            primary["design_full_rank"] = diagnostics["full_rank"]
            primary["support_adjusted"] = diagnostics["support_adjusted"]
            parts.append(primary)
        latex = render_term_table(outcome, pd.concat(parts, ignore_index=True))
        self.assertNotIn("-- & -- & --", latex)
        self.assertIn("18 estimable df rather than 20", latex)
        self.assertIn("Quorum--FIFA", latex)

    def test_six_workload_three_way_terms_are_reported_on_support(self):
        table = targeted_three_way_sensitivity(self.six)
        conditional = table.loc[table["component"] == "Conditional performance"]
        self.assertTrue(conditional["reported"].all())
        self.assertTrue((conditional["added_rank"] > 0).all())
        self.assertTrue((~conditional["fully_estimable"]).any())
        self.assertIn("reported on observed support", set(conditional["status"]))


if __name__ == "__main__":
    unittest.main()
