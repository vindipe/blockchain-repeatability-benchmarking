from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from analysis.audit_campaign_structure import (
    identifier_audit,
    run,
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

    def test_run_writes_provenance_outputs_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run(DEFAULT_INPUT, root / "outputs")
            self.assertEqual(result["review_point"], "R1.6")
            self.assertIn("provenance-only", result["scope"])
            for filename in (
                "campaign_identifier_audit.json",
                "configuration_hash_structure.csv",
                "summary.json",
            ):
                self.assertTrue((root / "outputs" / filename).is_file())
            self.assertFalse(
                (root / "outputs/campaign_variance_decomposition.csv").exists()
            )
            self.assertFalse((root / "outputs/campaign_variance_summary.csv").exists())
            self.assertFalse((root / "table.tex").exists())


if __name__ == "__main__":
    unittest.main()
