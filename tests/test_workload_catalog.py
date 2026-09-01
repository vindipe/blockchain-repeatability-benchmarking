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

    def test_run_writes_csv_json_and_latex(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = run(DEFAULT_INPUT, root / "outputs", root / "table.tex")
            self.assertEqual(summary["configuration_cells"], 300)
            self.assertTrue((root / "outputs" / "workload_catalog.csv").is_file())
            self.assertTrue((root / "outputs" / "summary.json").is_file())
            latex = (root / "table.tex").read_text(encoding="utf-8")
            self.assertIn(r"\label{tab:six_workload_catalog}", latex)
            self.assertNotIn(r"\color{olive}", latex)
            self.assertIn(r"\caption{\vd{M1/M2:", latex)
            self.assertEqual(latex.count(r"\vd{"), 1)
            self.assertIn("19,800 TPS at 0 s", latex)
            self.assertIn("DDoS denotes", latex)


if __name__ == "__main__":
    unittest.main()
