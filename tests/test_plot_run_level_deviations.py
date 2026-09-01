import unittest

from analysis.audit_observed_runs import DEFAULT_INPUT, load_runs
from analysis.derive_run_outcomes import derive_outcomes, prepare_selected_runs
from analysis.plot_run_level_deviations import (
    JITTER_HALF_WIDTH,
    deviation_frame,
    render_caption_replacements,
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

    def test_generated_m5_captions_are_revision_marked(self):
        captions = render_caption_replacements()
        self.assertEqual(captions.count(r"\caption{"), 6)
        self.assertEqual(captions.count(r"\vd{M1/M3/M5:"), 6)
        self.assertIn("one metric-eligible positive-service execution", captions)


if __name__ == "__main__":
    unittest.main()
