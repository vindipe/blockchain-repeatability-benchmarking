# Network-Controlled Blockchain Benchmarking Dataset

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17681717.svg)](https://doi.org/10.5281/zenodo.17681717)
![Data License: CC BY 4.0](https://img.shields.io/badge/data%20license-CC--BY--4.0-lightgrey.svg)

This repository contains the public dataset for evaluating the repeatability and performance predictability of blockchain benchmarks under controlled network conditions.

The dataset is associated with the ACM *Distributed Ledger Technologies: Research and Practice* article:

> Vincenzo P. Di Perna, Valerio Schiavoni, Miguel Matos, Francesco Fabris, Marco Bernardo.  
> **The Impact of Network Topology on Performance Metrics and Energy Consumption for Blockchains: Towards Repeatable Benchmarking.**  
> *Distributed Ledger Technologies: Research and Practice*, ACM, 2026.  
> DOI: <https://doi.org/10.1145/3828757>

The archival dataset is available on Zenodo:

> **Network-Controlled Dataset of Blockchain Benchmarks for Evaluating Repeatability and Performance Predictability.**  
> Concept DOI: <https://doi.org/10.5281/zenodo.17681717>  
> Current version DOI: <https://doi.org/10.5281/zenodo.21381461>

## What this repository contains

The released CSV contains one aggregate observation for every blockchain, topology, workload, and network-size configuration in the experimental matrix. Each row summarizes repeated executions through counts, means, extrema, quartiles, standard deviations, absolute ranges, and relative-dispersion measures.

The matrix covers:

- five blockchains: Algorand, Diem, Ethereum, Quorum, and Solana;
- five network topologies: fat-tree, full mesh, hypercube, scale-free, and torus;
- six workloads: DDoS, FIFA, GAFAM, Gaming, PayPal, and VISA;
- two network sizes: 10 and 40 nodes;
- throughput, latency, energy, and committed-transaction measurements.

The resulting dataset has 300 configuration rows and 50 columns. It contains aggregate statistics rather than the individual run-level traces.

## Repository structure

```text
.
├── README.md
├── CITATION.cff
├── LICENSE
├── dataset/
│   ├── README.md
│   └── reproducibility-dataset.csv
└── docs/
    ├── README-ACM-DLT.md
    ├── data_dictionary.md
    ├── methodology.md
    └── provenance.md
```

## Using the dataset

The complete released dataset is available at [`dataset/reproducibility-dataset.csv`](dataset/reproducibility-dataset.csv). It can be inspected with standard CSV, spreadsheet, statistical, or data-analysis tools. The repository preserves the archived data without adding an unofficial analysis or plotting implementation.

## Repeating the experiments

The experiments were conducted with [Lilith: A Topology-Aware Benchmark Tool for Blockchains](https://doi.org/10.5281/zenodo.11409100). The companion instructions preserved in [`docs/README-ACM-DLT.md`](docs/README-ACM-DLT.md) point to the Lilith release and its batched `multi-run.sh` execution workflow.

Consult the paper and Lilith artifact for the complete environment, deployment, workload, topology, and measurement methodology. This repository provides the released aggregate dataset and does not independently contain the complete Lilith execution environment or run-level measurements.

## Data notes

- `mode` identifies the network topology.
- The three `*_count` columns report the number of repeated observations contributing to the corresponding aggregate statistics; values range from 9 to 26.
- Forty-nine configurations report zero mean throughput and latency. Relative statistics that require division by those means are therefore blank where undefined.
- Energy relative-dispersion fields are complete for all 300 configurations.
- See [`docs/data_dictionary.md`](docs/data_dictionary.md) for every column and [`docs/provenance.md`](docs/provenance.md) for version and checksum information.

## License

The dataset and documentation are licensed under the Creative Commons Attribution 4.0 International license (CC BY 4.0). See [`LICENSE`](LICENSE).

## Citation

When reusing this repository, please cite both the Zenodo dataset and the associated ACM article.

```bibtex
@dataset{schiavoni_blockchain_repeatability_2026,
  author    = {Schiavoni, Valerio and Matos, Miguel and Fabris, Francesco and Bernardo, Marco and Di Perna, Vincenzo P.},
  title     = {Network-Controlled Dataset of Blockchain Benchmarks for Evaluating Repeatability and Performance Predictability},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.17681717},
  url       = {https://doi.org/10.5281/zenodo.17681717}
}
```

```bibtex
@article{diperna_network_topology_2026,
  author  = {Di Perna, Vincenzo P. and Schiavoni, Valerio and Matos, Miguel and Fabris, Francesco and Bernardo, Marco},
  title   = {The Impact of Network Topology on Performance Metrics and Energy Consumption for Blockchains: Towards Repeatable Benchmarking},
  journal = {Distributed Ledger Technologies: Research and Practice},
  year    = {2026},
  publisher = {Association for Computing Machinery},
  doi     = {10.1145/3828757},
  url     = {https://doi.org/10.1145/3828757}
}
```
