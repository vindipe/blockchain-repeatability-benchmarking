import unittest

from analysis.audit_observed_runs import DEFAULT_INPUT, load_runs
from analysis.derive_run_outcomes import derive_outcomes, prepare_selected_runs
from analysis.plot_run_level_deviations import deviation_frame


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


if __name__ == "__main__":
    unittest.main()
