import unittest

import numpy as np

from analysis.icc_by_blockchain import cluster_bootstrap, fit_random_intercept


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


if __name__ == "__main__":
    unittest.main()
