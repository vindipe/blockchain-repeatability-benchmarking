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
