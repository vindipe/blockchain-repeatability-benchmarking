from __future__ import annotations

import unittest
from pathlib import Path

from analysis.audit_topology_instances import audit, latex_table


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

    def test_generated_table_defines_every_reported_metric(self) -> None:
        rows, _ = audit(REPOSITORY_ROOT / "inputs" / "topologies")
        table = latex_table(rows)
        self.assertIn(r"\vd{R1.16:", table)
        self.assertIn(r"\footnotesize", table)
        self.assertIn(r"$\bar{p}_{e}$", table)
        self.assertIn("10- and 40-validator XMLs", table)


if __name__ == "__main__":
    unittest.main()
