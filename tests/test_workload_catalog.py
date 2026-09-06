import tempfile
import unittest
from pathlib import Path

from analysis.audit_observed_runs import DEFAULT_INPUT, load_runs
from analysis.derive_run_outcomes import derive_outcomes, prepare_selected_runs
from analysis.workload_catalog import build_catalog, run


class WorkloadCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.derived = derive_outcomes(prepare_selected_runs(load_runs(DEFAULT_INPUT)))

    def test_catalog_covers_complete_observed_corpus(self):
        catalog = build_catalog(self.derived)
        self.assertEqual(len(catalog), 6)
        self.assertEqual(catalog["configuration_cells"].sum(), 300)
        self.assertEqual(catalog["observed_executions"].sum(), 4080)
        self.assertEqual(catalog["positive_commit"].sum(), 3125)
        self.assertEqual(catalog["zero_commit"].sum(), 953)
        self.assertEqual(catalog["no_submission"].sum(), 2)

    def test_raw_workload_labels_are_auditable(self):
        catalog = build_catalog(self.derived).set_index("workload")
        self.assertEqual(catalog.loc["DDoS", "raw_label"], "10000")
        self.assertEqual(catalog.loc["FIFA", "raw_label"], "football")
        self.assertEqual(catalog.loc["Gaming", "raw_label"], "dota")

    def test_run_writes_csv_and_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = run(DEFAULT_INPUT, root / "outputs")
            self.assertEqual(summary["configuration_cells"], 300)
            self.assertTrue((root / "outputs" / "workload_catalog.csv").is_file())
            self.assertTrue((root / "outputs" / "summary.json").is_file())
            self.assertFalse((root / "table.tex").exists())


if __name__ == "__main__":
    unittest.main()
