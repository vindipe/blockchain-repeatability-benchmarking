# Network-Controlled Blockchain Benchmarking Dataset and Analysis

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17681717.svg)](https://doi.org/10.5281/zenodo.17681717)
![Data License: CC BY 4.0](https://img.shields.io/badge/data%20license-CC--BY--4.0-lightgrey.svg)

This repository contains the aggregate and repeated-execution datasets, together
with the Python analysis used to generate the repeatability tables and figures
for controlled, topology-aware blockchain benchmarking.

The artifact is associated with:

> Vincenzo P. Di Perna, Valerio Schiavoni, Miguel Matos, Francesco Fabris,
> Marco Bernardo.
>
> **The Impact of Network Topology on Performance Metrics and Energy Consumption
> for Blockchains: Towards Repeatable Benchmarking.**
>
> *Distributed Ledger Technologies: Research and Practice*, ACM, 2026.
>
> DOI: <https://doi.org/10.1145/3828757>

It also supports the run-to-run analysis in the IEEE Access manuscript
**Experimental Repeatability and Performance Predictability in
Network-Controlled Blockchain Evaluation**.

The archival record is available through the stable Zenodo concept DOI:
<https://doi.org/10.5281/zenodo.17681717>.

## Contents

```text
.
├── README.md
├── CITATION.cff
├── LICENSE
├── requirements.txt
├── analysis/
│   └── plot_reproducibility.py
├── dataset/
│   ├── README.md
│   ├── reproducibility-dataset.csv
│   └── reproducibility-runs.csv
├── docs/
│   ├── README-ACM-DLT.md
│   ├── data_dictionary.md
│   ├── methodology.md
│   ├── provenance.md
│   └── run_level_data_dictionary.md
└── outputs/
    └── .gitkeep
```

- `dataset/reproducibility-runs.csv` contains 4,105 repeated-execution
  observations and 26 raw columns.
- `dataset/reproducibility-dataset.csv` is the previously released aggregate
  dataset with 300 configurations and 50 columns.
- `analysis/plot_reproducibility.py` is the analysis script used to aggregate
  the repeated observations and generate the paper tables and figures.
- `outputs/` is populated when the analysis is run.

## Experimental matrix

The released measurements cover:

- five blockchains: Algorand, Diem, Ethereum Clique, Quorum IBFT, and Solana;
- five topologies: fat-tree, full mesh, hypercube, scale-free, and torus;
- six workloads: DDoS, FIFA, GAFAM, Gaming, PayPal, and VISA;
- two validator-set sizes: 10 and 40 nodes;
- throughput, latency, energy, and committed-transaction measurements.

The IEEE Access analysis focuses on GAFAM, PayPal, and VISA. The script also
retains the three additional workloads used by the broader ACM DLT artifact and
generates separate figures for them.

## Reproduce the analysis

Python 3.12 was used for the validation recorded in this release.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python analysis/plot_reproducibility.py
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python analysis\plot_reproducibility.py
```

The script can be launched from any working directory because input and output
paths are resolved relative to the repository.

It writes:

- `outputs/reproducibility-dataset.csv`;
- six LaTeX tables, including the repeatability summaries and ANOVA/ICC table;
- twelve figure variants, each in PNG and PDF format.

## Preserved analysis behavior

The scientific selection and aggregation logic of the analysis script has been
preserved. It:

1. maps the raw labels to the names used in the papers;
2. selects the `diablo`/2023, hop-based observations with 8 cores, 16 GB RAM,
   10 secondaries, and non-dynamic topology;
3. converts negative energy values to missing values before aggregation;
4. groups the selected observations by blockchain, topology, workload, and
   network size, together with the fixed configuration columns;
5. computes counts, means, extrema, quartiles, sample standard deviations,
   IQR-based measures, directional deviations, WCD summaries, factorial ANOVA,
   and ICC;
6. uses GAFAM, PayPal, and VISA for the primary IEEE Access summaries.

The raw `hash` column identifies benchmark campaigns. The published analysis
does not use `hash` as a grouping key and does not remove CSV rows with
`commit_number == 0` before configuration-level aggregation. These choices are
documented here to reproduce the supplied script exactly; no new campaign
selection or outcome-state reconstruction has been introduced in this release.

## Documentation

- [`dataset/README.md`](dataset/README.md) explains both CSV files.
- [`docs/data_dictionary.md`](docs/data_dictionary.md) documents the aggregate
  schema.
- [`docs/run_level_data_dictionary.md`](docs/run_level_data_dictionary.md)
  documents the repeated-execution schema.
- [`docs/methodology.md`](docs/methodology.md) describes the implemented
  selection and analysis flow.
- [`docs/provenance.md`](docs/provenance.md) records source files and checksums.

## Repeating the experiments

The measurements were produced with
[Lilith: A Topology-Aware Benchmark Tool for Blockchains](https://doi.org/10.5281/zenodo.11409100).
The companion instructions in
[`docs/README-ACM-DLT.md`](docs/README-ACM-DLT.md) point to the Lilith release
and its batched `multi-run.sh` workflow.

This repository reproduces the analysis from released measurements. Consult the
papers and Lilith artifact for the complete infrastructure, deployment,
workload, topology, and measurement methodology.

## License and citation

The datasets, analysis code, and documentation are released under the Creative
Commons Attribution 4.0 International license (CC BY 4.0). See
[`LICENSE`](LICENSE).

When reusing the artifact, cite both the Zenodo dataset and the associated ACM
article. Citation metadata is available in [`CITATION.cff`](CITATION.cff).
