from __future__ import annotations

import sys
import unittest

from analysis.run_revision_workflow import frozen_output_hashes, validate_frozen_results, workflow_commands


class RevisionWorkflowTests(unittest.TestCase):
    def test_workflow_contains_every_revision_stage_in_dependency_order(self):
        commands = workflow_commands(icc_workers=2)
        scripts = [command[1] for command in commands[:-1]]
        self.assertEqual(
            scripts,
            [
                "analysis/audit_observed_runs.py",
                "analysis/audit_topology_instances.py",
                "analysis/derive_run_outcomes.py",
                "analysis/compute_corrected_dispersion.py",
                "analysis/balanced_sensitivity.py",
                "analysis/bootstrap_dispersion_tables.py",
                "analysis/fit_two_part_models.py",
                "analysis/icc_by_blockchain.py",
                "analysis/audit_gafam_trace.py",
                "analysis/workload_catalog.py",
                "analysis/plot_run_level_deviations.py",
                "analysis/audit_campaign_structure.py",
                "analysis/generate_study_delta.py",
            ],
        )
        self.assertEqual(commands[7][-2:], ["--workers", "2"])
        self.assertEqual(commands[-1][0], sys.executable)
        self.assertEqual(commands[-1][1:4], ["-m", "unittest", "discover"])

    def test_frozen_results_match_reviewed_totals(self):
        checks = validate_frozen_results()
        self.assertEqual(checks["observed_executions"], 4080)
        self.assertEqual(checks["configuration_cells"], 300)
        self.assertEqual(checks["icc_bootstrap_failures"], 0)

    def test_manifest_does_not_hash_itself(self):
        hashes = frozen_output_hashes()
        self.assertNotIn("outputs/revision/clean_room_manifest.json", hashes)
        self.assertNotIn("paper_tables/six_workloads/table_acm_ieee_delta.tex", hashes)
        self.assertIn("paper_tables/six_workloads/table_topology_properties.tex", hashes)


if __name__ == "__main__":
    unittest.main()
