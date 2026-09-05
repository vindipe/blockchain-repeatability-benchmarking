from __future__ import annotations

import unittest
from pathlib import Path

from analysis.audit_topology_instances import (
    GENERATOR_SHA256,
    audit,
    latex_table,
    regeneration_commands,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class TopologyInstanceAuditTests(unittest.TestCase):
    def test_frozen_instances_have_expected_graph_properties(self) -> None:
        rows, manifest = audit(REPOSITORY_ROOT / "inputs" / "topologies")
        by_name = {row.topology: row for row in rows}

        self.assertEqual(set(by_name), {
            "Fat-tree", "Full mesh", "Hypercube", "Scale-free", "Torus"
        })
        self.assertEqual((by_name["Full mesh"].vertices, by_name["Full mesh"].edges), (10, 45))
        self.assertEqual(by_name["Full mesh"].edge_connectivity, 9)
        self.assertEqual((by_name["Fat-tree"].vertices, by_name["Fat-tree"].edges), (17, 18))
        self.assertEqual((by_name["Scale-free"].diameter, by_name["Scale-free"].edge_connectivity), (5, 1))
        self.assertEqual((by_name["Torus"].edges, by_name["Torus"].diameter), (19, 3))
        self.assertEqual(len(manifest["files"]), 10)
        self.assertEqual(
            GENERATOR_SHA256,
            "7c4a494135fb5d1072ce57dcadb63755224bb09f7a3c31af22eb7b59f0b08ac7",
        )
        self.assertEqual(manifest["provenance"]["verified_instances"], 10)
        self.assertEqual(manifest["provenance"]["commands"], regeneration_commands())
        self.assertEqual(len(regeneration_commands()), 10)

    def test_generated_table_defines_every_reported_metric(self) -> None:
        rows, _ = audit(REPOSITORY_ROOT / "inputs" / "topologies")
        table = latex_table(rows)
        caption = next(line for line in table.splitlines() if line.startswith(r"\caption{"))
        self.assertIn(r"\vd[R1.16]{", table)
        self.assertTrue(caption.endswith("only endpoint replication differs.}}"))
        self.assertIn(r"\TableFont", table)
        self.assertIn(r"\begin{table}[t]", table)
        self.assertNotIn(r"\begin{table*}", table)
        self.assertIn(r"\begin{tabular}{lrrrrrrr}", table)
        self.assertIn(r"$\bar{p}_{e}$", table)
        self.assertIn("Both validator sizes yield the same overlay", table)


if __name__ == "__main__":
    unittest.main()
