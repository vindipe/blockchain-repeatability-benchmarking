from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from analysis.generate_study_delta import ACM_DOI, ROWS, render_table, run, validate_evidence


class StudyDeltaTests(unittest.TestCase):
    def test_delta_excludes_previously_published_elements_from_novelty(self):
        joined = " ".join(row["published_in_acm_dlt"] for row in ROWS)
        self.assertIn("P0--P3", joined)
        self.assertIn("IQR\\%", joined)
        self.assertIn("factorial ANOVA", joined)
        self.assertIn("pooled ICC", joined)

    def test_completed_outputs_support_delta_claims(self):
        evidence = validate_evidence()
        self.assertEqual(evidence["observed_executions"], 4080)
        self.assertEqual(evidence["configuration_cells"], 300)
        self.assertEqual(evidence["balanced_bootstrap_repetitions"], 5000)
        self.assertEqual(evidence["icc_bootstrap_repetitions"], 1000)

    def test_table_marks_caption_only(self):
        latex = render_table()
        self.assertIn(r"\caption{\vd{M8/R2.5:", latex)
        self.assertEqual(latex.count(r"\vd{"), 1)
        self.assertNotIn(r"\color{olive}", latex)
        self.assertIn("Published in ACM DLT", latex)
        self.assertIn("New in this IEEE Access submission", latex)

    def test_run_writes_executed_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run(root / "outputs", root / "table.tex")
            self.assertEqual(result["published_article_doi"], ACM_DOI)
            self.assertEqual(result["comparison_rows"], 7)
            self.assertTrue((root / "outputs/acm_ieee_delta.csv").is_file())
            self.assertTrue((root / "outputs/study_delta.json").is_file())
            self.assertTrue((root / "table.tex").is_file())


if __name__ == "__main__":
    unittest.main()
