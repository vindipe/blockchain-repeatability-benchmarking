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
│   ├── audit_observed_runs.py
│   ├── balanced_sensitivity.py
│   ├── bootstrap_dispersion_tables.py
│   ├── compute_corrected_dispersion.py
│   ├── derive_run_outcomes.py
│   └── plot_reproducibility.py
├── dataset/
│   ├── README.md
│   ├── reproducibility-dataset.csv
│   └── reproducibility-runs.csv
├── docs/
│   ├── README-ACM-DLT.md
│   ├── data_dictionary.md
│   ├── derived_outcome_data_dictionary.md
│   ├── methodology.md
│   ├── provenance.md
│   └── run_level_data_dictionary.md
├── outputs/
│   └── .gitkeep
└── tests/
    ├── test_audit_observed_runs.py
    ├── test_balanced_sensitivity.py
    ├── test_bootstrap_dispersion_tables.py
    ├── test_compute_corrected_dispersion.py
    └── test_derive_run_outcomes.py
```

- `dataset/reproducibility-runs.csv` contains 4,105 repeated-execution
  observations and 26 raw columns.
- `dataset/reproducibility-dataset.csv` is the previously released aggregate
  dataset with 300 configurations and 50 columns.
- `analysis/plot_reproducibility.py` is the analysis script used to aggregate
  the repeated observations and generate the paper tables and figures.
- `analysis/audit_observed_runs.py` inventories the observed configuration and
  campaign structure without classifying outcomes or computing performance
  statistics.
- `analysis/derive_run_outcomes.py` derives observable execution states and
  metric-specific validity masks without inferring failures from absent logs.
- `analysis/compute_corrected_dispersion.py` applies those masks symmetrically
  to means, extrema, quartiles, sample standard deviations, and signed
  deviations.
- `analysis/balanced_sensitivity.py` repeats the analysis after sampling nine
  observed executions per configuration without replacement. Sampling occurs
  before outcome and metric eligibility checks, so the corresponding
  denominators remain explicit rather than being forced to nine.
- `analysis/bootstrap_dispersion_tables.py` resamples metric-eligible executions
  within configurations, propagates percentile intervals to unweighted means
  and medians across configuration cells, and writes standalone LaTeX tables.
- `outputs/` is populated when the analysis or audit is run.

## Experimental matrix

The released measurements cover:

- five blockchains: Algorand, Diem, Ethereum Clique, Quorum IBFT, and Solana;
- five topologies: fat-tree, full mesh, hypercube, scale-free, and torus;
- six workloads: DDoS, FIFA, GAFAM, Gaming, PayPal, and VISA;
- two validator-set sizes: 10 and 40 nodes;
- throughput, latency, energy, and committed-transaction measurements.

The released corpus contains all six workloads. The current plotting script
retains the earlier GAFAM, PayPal, and VISA summaries and generates separate
figures for the other three workloads. The M1 audit reports both the complete
six-workload corpus and that legacy three-workload subset so that their scopes
cannot be confused.

## Reproduce the analysis

Python 3.12 was used for the validation recorded in this release.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 analysis/derive_run_outcomes.py
python3 analysis/compute_corrected_dispersion.py
python3 analysis/balanced_sensitivity.py
python3 analysis/bootstrap_dispersion_tables.py
```

The script can be launched from any working directory because input and output
paths are resolved relative to the repository.

Audit the observed design and run its regression tests with:

```bash
python3 analysis/audit_observed_runs.py
python3 analysis/derive_run_outcomes.py
python3 analysis/compute_corrected_dispersion.py
python3 analysis/balanced_sensitivity.py
python3 analysis/bootstrap_dispersion_tables.py
python3 -m unittest discover -s tests -v
```

The legacy plotting script remains available to reproduce the earlier released
outputs, but it is not the source of corrected M3 results. It writes:

- `outputs/reproducibility-dataset.csv`;
- six LaTeX tables, including the repeatability summaries and ANOVA/ICC table;
- twelve figure variants, each in PNG and PDF format.

## Current analysis and observed-design audit

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

The separate M1 audit applies the same fixed filters and verifies the design
before any outcome or metric processing. It finds 4,080 observed executions in
300 six-workload configurations, with configuration-level counts from 9 to 26;
only four configurations contain exactly 10 observations. The legacy
three-workload subset contains 2,053 observations in 150 configurations, of
which only two contain exactly 10 observations. Because no complete scheduling
manifest is available, the artifact reports observed rather than scheduled
attempt counts. No observations are synthesized or discarded to force a fixed
cell size.

The raw `hash` column identifies benchmark campaigns. The original plotting
script does not use `hash` as a grouping key and does not remove CSV rows with
`commit_number == 0` before configuration-level aggregation. M2 adds a separate
derived layer rather than overwriting that script or either released CSV. It
classifies 3,125 positive-commit executions, 953 submitted zero-commit
executions, and two no-submission executions. It does not label any row as a
technical failure because deployment and execution logs are not available.

Throughput and block latency are valid for conditional performance analysis
only when a positive commit is observed. Energy and network measurements remain
available for all 4,080 selected executions, including zero-commit and
no-submission outcomes. Seven positive-commit rows have stored TPS equal to
`0.0` because Diablo exported TPS with one decimal place. The released files do
not contain Diablo's last-event time, so the exact positive value cannot be
reconstructed. M3 retains these runs as positive-commit outcomes, labels their
TPS as left-censored (`0 < TPS < 0.05`), and excludes only those seven TPS
values from point-valued dispersion statistics.

M3 writes a long-form table with one row per configuration and metric to
`outputs/revision/m3_dispersion/configuration_metric_statistics.csv`. Every
statistic in a row uses the same eligibility mask. Signed relative deviations
are `100 * (y - mean) / mean`; the implementation verifies the `-100%` lower
bound and the `100(n-1)%` upper bound for non-negative observations. Sample
standard deviation is computed with `ddof=1` and is undefined when fewer than
two metric values are available.

The balanced sensitivity analysis uses all 300 configurations, each of which
contains at least nine observed executions. It performs 5,000 repetitions with
seed `20260830`. In every repetition it draws nine real rows per configuration
without replacement and only then applies the derived outcome and
metric-eligibility masks. It writes configuration-, factor-, denominator-, and
extrema-level comparisons to `outputs/revision/balanced_n9/`. The raw datasets
are never modified and no synthetic row is created.

M4/M7 uncertainty is computed separately from the balanced sensitivity.
`bootstrap_dispersion_tables.py` uses 5,000 within-configuration bootstrap
replicates and seed `20260831`. For each metric/configuration cell, it resamples
the metric-eligible executions with replacement at their original count,
recomputes IQR% and sample-Std%, and propagates the replicates to both the
unweighted mean and median across cells. It reports 95% percentile intervals,
the number of contributing configuration cells, total metric observations, and
the metric-specific run-count range. Cells with fewer than two eligible values
do not contribute a dispersion estimate. The script writes machine-readable
CSV files and 18 standalone LaTeX tables: nine for the six-workload corpus and
nine for the legacy three-workload subset.

## Documentation

- [`dataset/README.md`](dataset/README.md) explains both CSV files.
- [`docs/data_dictionary.md`](docs/data_dictionary.md) documents the aggregate
  schema.
- [`docs/run_level_data_dictionary.md`](docs/run_level_data_dictionary.md)
  documents the repeated-execution schema.
- [`docs/derived_outcome_data_dictionary.md`](docs/derived_outcome_data_dictionary.md)
  documents the M2 status and metric-validity fields.
- [`docs/methodology.md`](docs/methodology.md) describes the implemented
  selection, observed-design audit, and analysis flow.
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
