# Provenance and Versioning

This repository mirrors the published files associated with the Zenodo concept
DOI and adds the repeated-execution dataset, the analysis script used for the
paper outputs, dependency metadata, and expanded documentation.

## Zenodo identifiers

| Purpose | DOI | Record |
|---|---|---|
| Stable concept DOI (all versions) | `10.5281/zenodo.17681717` | `17681717` |
| Initial archived version | `10.5281/zenodo.17681718` | `17681718` |
| Preceding archived version | `10.5281/zenodo.21381461` | `21381461` |

The concept DOI remains the stable citation across versions. Zenodo assigns a
new immutable version DOI when the updated package is published.

The preceding version was published on 15 July 2026 with the aggregate dataset,
ACM DLT companion instructions, and complete creator metadata.

## Source and integrity

The aggregate dataset and ACM DLT instructions were downloaded from Zenodo
record `21381461`. Their checksums match the values recorded by that version.

The repeated-execution CSV and Python script were supplied by the authors for
this update. The script received only repository-integration changes:

- repository-relative input and output paths;
- creation of the output directory before the first write;
- a headless Matplotlib backend;
- exact removal of the terminal topology suffix with a regular expression.

The selection, aggregation, statistical calculations, tables, and plots were
otherwise preserved.

## Released files

| Path | Size (bytes) | MD5 | SHA-256 |
|---|---:|---|---|
| `dataset/reproducibility-dataset.csv` | 102,947 | `b64465d9abf6508aad4c61af2c18bd2c` | `e47cf295d17a04134845b66ff9aae14e62e199561c51968fd37576e1b1c13b20` |
| `dataset/reproducibility-runs.csv` | 639,261 | `11e05ccd13fa906d095ce780b9228b0c` | `c520ec25a02f2bc7e8c719c8b2dd0524c4c6a11d1d53953d77bb361d3f96b765` |
| `analysis/plot_reproducibility.py` | 54,074 | `b03204dc6a934ee3381652e27cc848be` | `c4fbe7cbd5cf553588777ad15a8704dabca32c24d2fc00a8b92189c5b3635b45` |
| `requirements.txt` | 109 | `0b52c891589e19def8d4e039c0c5993f` | `406ac924eaf91ee26b670382c8361d9bf29bc8afd6fee33c47db20788271152d` |
| `docs/README-ACM-DLT.md` | 413 | `39c635e0d697e5fc0da310e0368a765d` | `22d21b4d5d17f3035e2e1ba14ae5b0af0a66ffc0ed74f985e853a89d64ada3c6` |

## GAFAM workload input (m2)

The GAFAM workload definition is mirrored from
`https://github.com/vindipe/lilith`, commit
`dd1d457c6079661b158f601cdf70817cbe2a5f2a`, path
`kollaps/examples/diablo/primary/fixes/workload-gafam-long.yaml`. Its upstream
SHA-256 is
`11fd627b4fba15884605b1fda1e11d701b10538b9f1ccf9e61fd458e2aff17ba`.
The packaged mirror adds one terminating LF without changing the YAML content;
its SHA-256 is
`11d4fb66ef30608764bb91ee8fb62ecddc294c6d19fc2d8ba7cd9e71d7ce83b7`.

Lilith's execution loop selects `workload-gafam-long.yaml` for the `gafam`
workload. The released CSV retains the raw `gafam` label but does not contain a
historical execution manifest with a trace checksum. The artifact therefore
records both links explicitly and does not claim a cryptographic binding that
the released run rows themselves cannot establish.

## Network trace and topology XMLs (m9)

The selected raw label `dataset=diablo` refers to the 2023 AWS RTT-trace
vintage. The exact versioned input is Lilith
`misc/diablo-aws.csv` at commit
`dd1d457c6079661b158f601cdf70817cbe2a5f2a`, SHA-256
`c7f384cf276666293d275d4c5056dface1d6271f54e449fd9629024b7ab1b7d3`.
It is mirrored under `inputs/topologies/`. This label is independent of
`start_bench`, whose selected campaign timestamps span 21 April 2024 through
8 August 2025.

Lilith creates `topology.xml` at runtime and does not version generated XMLs.
The ten files under `inputs/topologies/` were regenerated with the versioned
generator at the frozen Lilith commit, `scripts/gen_topo.py` (SHA-256
`7c4a494135fb5d1072ce57dcadb63755224bb09f7a3c31af22eb7b59f0b08ac7`),
the frozen trace above, and `misc/sample-topology.xml` (SHA-256
`62bd7fedfd311482a376049a6e1e4b661fb8f25165ddeb263830f70a397b3816`).
For each topology type (`fat-tree-l`, `full-mesh`, `hypercube`, `scale-free-l`,
and `torus-l`) and each `--nodes` value (`1` and `4`), regeneration used:

```text
python3 scripts/gen_topo.py --secondaries 10 --nodes <1|4> --bandwidth 1 \
  --type <topology> --strategy hop --dataset diablo --dynamic 0 \
  --blockchain poa
```

The ten resulting `kollaps/examples/topology.xml` files are byte-identical to
the frozen XMLs. Their checksums, the exact command lines, the verified instance
count, and the contraction rule are recorded in
`outputs/revision/m9_topology_audit/topology_audit.json`.

## Validation

The artifact was validated on 29 July 2026 with Python 3.12 and the pinned
dependencies in `requirements.txt`.

The complete script executed successfully and produced:

- one 300-row, 50-column aggregate CSV;
- six LaTeX tables;
- twelve PNG figures;
- twelve PDF figures.

The generated `outputs/reproducibility-dataset.csv` is byte-identical to
`dataset/reproducibility-dataset.csv` and has SHA-256:

```text
e47cf295d17a04134845b66ff9aae14e62e199561c51968fd37576e1b1c13b20
```

This confirms that the repository-integration changes do not alter the released
aggregate dataset.

## Artifact scope

The artifact reproduces the analysis, figures, and tables from the released
measurements. It does not include the complete Lilith deployment and execution
infrastructure. The Lilith source and execution workflow remain available at:
<https://doi.org/10.5281/zenodo.11409100>.
