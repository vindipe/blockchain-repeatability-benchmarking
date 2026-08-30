# Datasets

This directory contains both the repeated-execution input and the
configuration-level aggregate dataset.

## `reproducibility-runs.csv`

The run-level release contains 4,105 rows and 26 columns. Each row is a
measurement exported by the benchmark pipeline and includes:

- campaign identifier (`hash`) and run number;
- blockchain, topology, workload, dataset, and infrastructure fields;
- submitted, committed, and aborted transaction counts;
- load, throughput, latency, energy, and network measurements;
- benchmark start timestamp.

The file preserves all supplied rows, including rows with
`commit_number == 0`. Applying the fixed experimental filters selects 4,080
observed executions across 300 configurations. Their observed cell sizes range
from 9 to 26; they are not a balanced ten-run design. See
[`../docs/run_level_data_dictionary.md`](../docs/run_level_data_dictionary.md)
for the schema and [`../docs/methodology.md`](../docs/methodology.md) for the
selection performed by the analysis script.

## `reproducibility-dataset.csv`

This is the 300-row, 50-column aggregate dataset published in the preceding
Zenodo version. Each row is identified by:

```text
blockchain, mode, workload, network_size
```

The complete matrix is:

```text
5 blockchains x 5 topologies x 6 workloads x 2 network sizes = 300 rows
```

For throughput, latency, and energy, the CSV reports observation counts, means,
extrema, quartiles, standard deviations, absolute ranges, and relative
dispersion measures. `commit_number_mean` reports the mean committed-transaction
count.

Running `analysis/plot_reproducibility.py` produces a fresh copy at
`outputs/reproducibility-dataset.csv`. See
[`../docs/data_dictionary.md`](../docs/data_dictionary.md) for the aggregate
schema.
