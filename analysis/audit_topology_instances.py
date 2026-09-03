"""Audit the exact Lilith XML topology instances used by the study (R1.16).

The XML files are deterministic regenerations from Lilith commit
``dd1d457c6079661b158f601cdf70817cbe2a5f2a`` and its versioned
``diablo-aws.csv`` input.  Workload services are endpoint leaves, while
numbered ``s<N>`` bridges are hop-emulation nodes inserted along one logical
edge.  This audit removes the former and contracts the latter.  Structural
branching bridges (including fat-tree gates) remain part of the audited
overlay graph.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = REPOSITORY_ROOT / "inputs" / "topologies"
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "m9_topology_audit"
DEFAULT_PAPER_TABLE = (
    REPOSITORY_ROOT / "paper_tables" / "six_workloads" / "table_topology_properties.tex"
)

LILITH_COMMIT = "dd1d457c6079661b158f601cdf70817cbe2a5f2a"
GENERATOR_SHA256 = "e9c23f7b923867648b8401ccdc09f4a0e7de62c8a685e5eff0b15e73a1779ada"
TRACE_SHA256 = "c7f384cf276666293d275d4c5056dface1d6271f54e449fd9629024b7ab1b7d3"
TEMPLATE_SHA256 = "62bd7fedfd311482a376049a6e1e4b661fb8f25165ddeb263830f70a397b3816"

TOPOLOGIES = {
    "fat-tree-l": "Fat-tree",
    "full-mesh": "Full mesh",
    "hypercube": "Hypercube",
    "scale-free-l": "Scale-free",
    "torus-l": "Torus",
}
SIZE_CODES = {1: 10, 4: 40}
HOP_BRIDGE = re.compile(r"s\d+")
VALIDATOR_SERVICE = re.compile(r".+-n\d+")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class OverlayGraph:
    nodes: frozenset[str]
    edges: frozenset[tuple[str, str]]
    validators: int


@dataclass(frozen=True)
class TopologyMetrics:
    topology: str
    validator_sizes: str
    vertices: int
    edges: int
    degree_min: int
    degree_median: float
    degree_max: int
    diameter: int
    average_shortest_path: float
    edge_connectivity: int
    average_pairwise_edge_disjoint_paths: float


def canonical_edge(left: str, right: str) -> tuple[str, str]:
    if left == right:
        raise ValueError(f"Self-loop after contraction: {left}")
    return tuple(sorted((left, right)))


def parse_overlay(path: Path) -> OverlayGraph:
    root = ET.parse(path).getroot()
    bridges = {
        element.attrib["name"] for element in root.findall(".//bridges/bridge")
    }
    retained = {name for name in bridges if HOP_BRIDGE.fullmatch(name) is None}
    hop_nodes = bridges.difference(retained)

    validators = {
        element.attrib["name"]
        for element in root.findall(".//services/service")
        if VALIDATOR_SERVICE.fullmatch(element.attrib.get("name", ""))
    }

    adjacency: dict[str, set[str]] = defaultdict(set)
    for element in root.findall(".//links/link"):
        left = element.attrib["origin"]
        right = element.attrib["dest"]
        if left in bridges and right in bridges:
            adjacency[left].add(right)
            adjacency[right].add(left)

    logical_edges: set[tuple[str, str]] = set()
    for left in retained:
        for right in adjacency[left].intersection(retained):
            logical_edges.add(canonical_edge(left, right))

    visited: set[str] = set()
    for start in sorted(hop_nodes):
        if start in visited:
            continue
        visited.add(start)
        queue = [start]
        boundary: set[str] = set()
        while queue:
            node = queue.pop()
            for neighbour in adjacency[node]:
                if neighbour in retained:
                    boundary.add(neighbour)
                elif neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(neighbour)
        if len(boundary) != 2:
            raise ValueError(
                f"Hop-node component in {path.name} has {len(boundary)} logical "
                f"endpoints instead of 2: {sorted(boundary)}"
            )
        logical_edges.add(canonical_edge(*sorted(boundary)))

    graph = OverlayGraph(
        nodes=frozenset(retained),
        edges=frozenset(logical_edges),
        validators=len(validators),
    )
    validate_connected(graph, path.name)
    return graph


def adjacency(graph: OverlayGraph) -> dict[str, set[str]]:
    result = {node: set() for node in graph.nodes}
    for left, right in graph.edges:
        result[left].add(right)
        result[right].add(left)
    return result


def shortest_paths(graph: OverlayGraph, source: str) -> dict[str, int]:
    neighbours = adjacency(graph)
    distances = {source: 0}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        for neighbour in neighbours[node]:
            if neighbour not in distances:
                distances[neighbour] = distances[node] + 1
                queue.append(neighbour)
    return distances


def validate_connected(graph: OverlayGraph, label: str) -> None:
    if not graph.nodes:
        raise ValueError(f"No logical topology nodes in {label}")
    reached = shortest_paths(graph, min(graph.nodes))
    if len(reached) != len(graph.nodes):
        missing = sorted(graph.nodes.difference(reached))
        raise ValueError(f"Disconnected topology in {label}; unreachable: {missing}")


def edge_disjoint_paths(graph: OverlayGraph, source: str, sink: str) -> int:
    """Return unit-capacity undirected max flow using Edmonds--Karp."""

    residual: dict[tuple[str, str], int] = defaultdict(int)
    neighbours: dict[str, set[str]] = defaultdict(set)
    for left, right in graph.edges:
        residual[left, right] += 1
        residual[right, left] += 1
        neighbours[left].add(right)
        neighbours[right].add(left)

    flow = 0
    while True:
        parent: dict[str, str | None] = {source: None}
        queue = deque([source])
        while queue and sink not in parent:
            node = queue.popleft()
            for neighbour in sorted(neighbours[node]):
                if neighbour not in parent and residual[node, neighbour] > 0:
                    parent[neighbour] = node
                    queue.append(neighbour)
        if sink not in parent:
            return flow
        node = sink
        while parent[node] is not None:
            previous = parent[node]
            residual[previous, node] -= 1
            residual[node, previous] += 1
            neighbours[node].add(previous)
            neighbours[previous].add(node)
            node = previous
        flow += 1


def compute_metrics(name: str, graph: OverlayGraph) -> TopologyMetrics:
    nodes = sorted(graph.nodes)
    degrees = sorted(len(values) for values in adjacency(graph).values())
    pair_distances: list[int] = []
    pair_connectivities: list[int] = []
    for index, source in enumerate(nodes):
        distances = shortest_paths(graph, source)
        for sink in nodes[index + 1 :]:
            pair_distances.append(distances[sink])
            pair_connectivities.append(edge_disjoint_paths(graph, source, sink))
    return TopologyMetrics(
        topology=name,
        validator_sizes="10/40",
        vertices=len(nodes),
        edges=len(graph.edges),
        degree_min=min(degrees),
        degree_median=float(statistics.median(degrees)),
        degree_max=max(degrees),
        diameter=max(pair_distances),
        average_shortest_path=sum(pair_distances) / len(pair_distances),
        edge_connectivity=min(pair_connectivities),
        average_pairwise_edge_disjoint_paths=(
            sum(pair_connectivities) / len(pair_connectivities)
        ),
    )


def format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}"


def latex_table(rows: Iterable[TopologyMetrics]) -> str:
    lines = [
        r"\begin{table}[t]",
        r"\caption{\vd{R1.16: Numerical audit of the instantiated topology XMLs. $V/E$: vertices/undirected edges; degree: min/median/max; $\bar{\ell}$: average shortest-path length; $\lambda$: global edge connectivity; $\bar{p}_{e}$: mean pairwise edge-disjoint paths. Workload leaves are excluded and numbered hop bridges contracted. Both validator sizes yield the same overlay; only endpoint replication differs.}}",
        r"\label{tab:topology_numeric_audit}",
        r"\centering",
        r"\TableFont",
        r"\setlength{\tabcolsep}{3.6pt}",
        r"\begin{tabular}{lrrrrrrr}",
        r"\toprule",
        r"Topology & $V$ & $E$ & Degree & Diam. & $\bar{\ell}$ & $\lambda$ & $\bar{p}_{e}$ \\",
        r"\midrule",
    ]
    for row in rows:
        degree = (
            f"{row.degree_min}/{format_number(row.degree_median)}/{row.degree_max}"
        )
        lines.append(
            f"{row.topology} & {row.vertices} & {row.edges} & {degree} & "
            f"{row.diameter} & {row.average_shortest_path:.2f} & "
            f"{row.edge_connectivity} & "
            f"{row.average_pairwise_edge_disjoint_paths:.2f} \\\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
            "",
        ]
    )
    return "\n".join(lines)


def audit(input_dir: Path) -> tuple[list[TopologyMetrics], dict[str, object]]:
    trace_path = input_dir / "diablo-aws.csv"
    if sha256_file(trace_path) != TRACE_SHA256:
        raise ValueError(f"Unexpected checksum for {trace_path}")

    metrics: list[TopologyMetrics] = []
    files: dict[str, object] = {}
    for raw_name, display_name in TOPOLOGIES.items():
        instances: dict[int, OverlayGraph] = {}
        for size_code, validators in SIZE_CODES.items():
            path = input_dir / f"{raw_name}_{size_code}.xml"
            graph = parse_overlay(path)
            if graph.validators != validators:
                raise ValueError(
                    f"{path.name} contains {graph.validators} validators; expected {validators}"
                )
            instances[size_code] = graph
            files[path.name] = {
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "validators": graph.validators,
                "contracted_vertices": len(graph.nodes),
                "contracted_edges": len(graph.edges),
            }
        first = instances[1]
        second = instances[4]
        if first.nodes != second.nodes or first.edges != second.edges:
            raise ValueError(f"Overlay differs between sizes for {display_name}")
        metrics.append(compute_metrics(display_name, first))

    manifest = {
        "method": {
            "graph": "undirected simple contracted overlay",
            "excluded": "workload-service endpoint leaves",
            "contracted": "numbered s<N> hop-emulation bridges",
            "retained": "regional and structural branching bridges",
            "path_diversity": "mean unit-capacity edge-disjoint paths over unordered vertex pairs",
        },
        "provenance": {
            "lilith_repository": "https://github.com/vindipe/lilith",
            "lilith_commit": LILITH_COMMIT,
            "generator_path": "scripts/gen_topo.py",
            "generator_sha256": GENERATOR_SHA256,
            "trace_path": "misc/diablo-aws.csv",
            "trace_sha256": TRACE_SHA256,
            "template_path": "misc/sample-topology.xml",
            "template_sha256": TEMPLATE_SHA256,
            "regeneration": "deterministic regeneration from the frozen source revision and input",
        },
        "files": files,
        "metrics": [asdict(row) for row in metrics],
    }
    return metrics, manifest


def write_outputs(
    metrics: list[TopologyMetrics],
    manifest: dict[str, object],
    output_dir: Path,
    paper_table: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [asdict(row) for row in metrics]
    with (output_dir / "topology_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "topology_audit.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    table = latex_table(metrics)
    (output_dir / "table_topology_properties.tex").write_text(
        table, encoding="utf-8"
    )
    paper_table.parent.mkdir(parents=True, exist_ok=True)
    paper_table.write_text(table, encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--paper-table", type=Path, default=DEFAULT_PAPER_TABLE)
    parser.add_argument("--check-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    metrics, manifest = audit(args.input_dir)
    if not args.check_only:
        write_outputs(metrics, manifest, args.output_dir, args.paper_table)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
