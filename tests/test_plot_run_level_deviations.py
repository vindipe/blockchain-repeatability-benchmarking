import unittest

from analysis.audit_observed_runs import DEFAULT_INPUT, load_runs
from analysis.derive_run_outcomes import derive_outcomes, prepare_selected_runs
from analysis.plot_run_level_deviations import (
    DEVIATION_FIGURE_SIZE,
    FINAL_PLACEMENT_FRACTION,
    JITTER_HALF_WIDTH,
    SOURCE_MINIMUM_TEXT_PT,
    deviation_frame,
    outcome_figure_frame,
    render_caption_replacements,
    render_outcome_table,
)


class RunLevelDeviationPlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.derived = derive_outcomes(prepare_selected_runs(load_runs(DEFAULT_INPUT)))

    def test_metric_eligibility_counts_are_preserved(self):
        self.assertEqual(len(deviation_frame(self.derived, "tps")), 3118)
        self.assertEqual(len(deviation_frame(self.derived, "latency")), 3125)
        self.assertEqual(len(deviation_frame(self.derived, "energy")), 3125)

    def test_signed_deviations_center_within_configuration(self):
        for metric in ("tps", "latency", "energy"):
            deviations = deviation_frame(self.derived, metric)
            centered = deviations.groupby(
                ["blockchain", "mode", "workload", "network_size"], observed=True
            )["absolute_deviation"].sum()
            self.assertLess(centered.abs().max(), 1e-8)

    def test_each_eligible_execution_has_a_distinct_horizontal_position(self):
        for metric in ("tps", "latency", "energy"):
            deviations = deviation_frame(self.derived, metric)
            self.assertLessEqual(
                deviations["plot_offset"].abs().max(), JITTER_HALF_WIDTH + 1e-12
            )
            duplicated = deviations.duplicated(
                ["blockchain", "mode", "workload", "network_size", "plot_x"]
            )
            self.assertFalse(duplicated.any())

    def test_point_identity_is_preserved_for_auditing(self):
        deviations = deviation_frame(self.derived, "tps")
        self.assertFalse(
            deviations.duplicated(
                [
                    "dataset",
                    "run",
                    "hash",
                    "blockchain",
                    "mode",
                    "workload",
                    "network_size",
                ]
            ).any()
        )

    def test_generated_r1_5_captions_are_revision_marked(self):
        captions = render_caption_replacements()
        self.assertEqual(captions.count(r"\caption{"), 7)
        self.assertEqual(captions.count(r"\vd{R1.5/R2.6:"), 7)
        self.assertIn("one point-valued positive-service TPS execution", captions)
        self.assertIn("positive-commit/zero-commit/no-submission", captions)

    def test_outcome_figure_has_one_exact_cell_per_configuration(self):
        counts = outcome_figure_frame(self.derived)
        self.assertEqual(len(counts), 300)
        self.assertFalse(
            counts.duplicated(
                ["blockchain", "mode", "workload", "network_size"]
            ).any()
        )
        self.assertEqual(counts["n_observed"].sum(), 4080)
        self.assertEqual(counts["n_positive_commit"].sum(), 3125)
        self.assertEqual(counts["n_zero_commit"].sum(), 953)
        self.assertEqual(counts["n_no_submission"].sum(), 2)
        self.assertTrue(
            (
                counts["display_count"]
                == counts.apply(
                    lambda row: (
                        f"{row['n_positive_commit']}/"
                        f"{row['n_zero_commit']}/"
                        f"{row['n_no_submission']}"
                    ),
                    axis=1,
                )
            ).all()
        )

    def test_outcome_table_reconciles_outcomes_and_metric_validity(self):
        table = render_outcome_table(outcome_figure_frame(self.derived))
        self.assertIn(r"\caption{\vd{R1.5/R2.6:", table)
        self.assertIn(r"\footnotesize", table)
        self.assertIn(
            "Total & -- & 300 & 4080 & 4078 & 3125 & 953 & 2 & 3118 & 3125 & 3125",
            table,
        )
        self.assertNotIn(r"\color{olive}", table)

    def test_final_layout_uses_readable_source_typography(self):
        self.assertEqual(DEVIATION_FIGURE_SIZE, (10.2, 5.6))
        self.assertEqual(FINAL_PLACEMENT_FRACTION, 1.0)
        self.assertGreaterEqual(SOURCE_MINIMUM_TEXT_PT, 11.5)


if __name__ == "__main__":
    unittest.main()
