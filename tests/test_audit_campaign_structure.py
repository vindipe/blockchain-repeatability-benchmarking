from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from analysis.audit_campaign_structure import (
    identifier_audit,
    render_table,
    run,
    summarize_decomposition,
    variance_decomposition,
)
from analysis.audit_observed_runs import DEFAULT_INPUT, load_runs
from analysis.derive_run_outcomes import derive_outcomes, prepare_selected_runs


class CampaignStructureAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.derived = derive_outcomes(prepare_selected_runs(load_runs(DEFAULT_INPUT)))

    def test_identifier_structure_is_not_a_crossed_campaign_factor(self):
        audit, structure = identifier_audit(self.derived)
        self.assertEqual(audit["hash_batches"], 1006)
        self.assertTrue(audit["each_hash_maps_to_one_configuration"])
        self.assertTrue(audit["dataset_is_constant"])
        self.assertTrue(audit["hash_run_pair_is_unique"])
        self.assertEqual(audit["singleton_hash_batches"], 386)
        self.assertEqual(audit["repeated_hash_batches"], 620)
        self.assertEqual(len(structure), 300)

    def test_decomposition_reconstructs_total_sum_of_squares(self):
        decomposition = variance_decomposition(self.derived)
        self.assertLess(decomposition["decomposition_identity_error"].max(), 1e-7)
        summary = summarize_decomposition(decomposition)
        self.assertEqual(set(summary["strict_configurations"]), {221})
        self.assertEqual(set(summary["decomposable_configurations"]), {245})

    def test_generated_table_marks_caption_only(self):
        summary = summarize_decomposition(variance_decomposition(self.derived))
        latex = render_table(summary)
        self.assertNotIn(r"\color{olive}", latex)
        self.assertIn(r"\caption{\vd{M6:", latex)
        self.assertEqual(latex.count(r"\vd{"), 1)
        self.assertIn(r"\label{tab:campaign_hash_sensitivity}", latex)

    def test_run_writes_machine_readable_outputs_and_table(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run(DEFAULT_INPUT, root / "outputs", root / "table.tex")
            self.assertEqual(result["review_point"], "M6")
            for filename in (
                "campaign_identifier_audit.json",
                "configuration_hash_structure.csv",
                "campaign_variance_decomposition.csv",
                "campaign_variance_summary.csv",
                "summary.json",
            ):
                self.assertTrue((root / "outputs" / filename).is_file())
            self.assertTrue((root / "table.tex").is_file())


if __name__ == "__main__":
    unittest.main()
