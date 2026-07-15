# Dataset

`reproducibility-dataset.csv` is the public aggregate dataset archived in the current Zenodo release.

## Experimental matrix

Each row is uniquely identified by:

```text
blockchain, mode, workload, network_size
```

The complete factorial matrix contains:

```text
5 blockchains x 5 topologies x 6 workloads x 2 network sizes = 300 rows
```

The other configuration fields are constant in this release: 8 CPU cores, 16 GB RAM, 10 secondaries, the 2023 workload dataset, hop-based link strategy, and non-dynamic topology.

## Measurements

For throughput, latency, and energy, the CSV reports:

- observation count;
- mean, maximum, minimum, first quartile, third quartile, and standard deviation;
- relative minimum and maximum deviation from the mean;
- interquartile range and its percentage of the mean;
- absolute range and standard deviation as a percentage of the mean.

`commit_number_mean` reports the mean number of committed transactions.

Relative fields are blank when the corresponding mean or denominator makes the statistic undefined. See [`../docs/data_dictionary.md`](../docs/data_dictionary.md) for the complete schema.
