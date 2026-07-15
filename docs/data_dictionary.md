# Data Dictionary

The CSV has 50 columns grouped into configuration, aggregate measurements, and repeatability/dispersion statistics.

## Configuration columns

| Column | Meaning |
|---|---|
| `blockchain` | Blockchain implementation: Algorand, Diem, Ethereum, Quorum, or Solana. |
| `mode` | Controlled network topology: fat-tree, full mesh, hypercube, scale-free, or torus. |
| `workload` | Workload profile: DDoS, FIFA, GAFAM, Gaming, PayPal, or VISA. |
| `cores` | CPU cores allocated to the experiment; 8 in this release. |
| `ram` | RAM allocation in GB; 16 in this release. |
| `secondaries` | Number of secondary instances/processes configured; 10 in this release. |
| `dataset` | Workload dataset identifier; 2023 in this release. |
| `link_strategy` | Network-link strategy; `hop` in this release. |
| `network_size` | Network size: `10 nodes` or `40 nodes`. |
| `dynamic` | Dynamic-topology flag; 0 (disabled) in this release. |

## Base aggregate columns

The prefixes `average_throughput`, `average_latency`, and `energy` each use the following suffixes:

| Suffix | Meaning |
|---|---|
| `_count` | Number of repeated observations included in the aggregate. |
| `_mean` | Arithmetic mean. |
| `_max` | Maximum observed value. |
| `_min` | Minimum observed value. |
| `_q25` | First quartile (25th percentile). |
| `_q75` | Third quartile (75th percentile). |
| `_std` | Standard deviation. |

`commit_number_mean` is the mean number of committed transactions for the configuration.

Units follow the experiment and paper conventions:

- throughput: transactions per second;
- latency: seconds;
- energy: the aggregate energy measure exported by the Lilith experiment pipeline;
- committed transactions: transaction count.

## Repeatability and dispersion columns

For each of `average_throughput`, `average_latency`, and `energy`, the following derived suffixes are reported:

| Suffix | Meaning |
|---|---|
| `_min_perc` | Percentage deviation of the minimum from the mean. |
| `_max_perc` | Percentage deviation of the maximum from the mean. |
| `_iqr` | Interquartile range, `q75 - q25`. |
| `_iqr_perc` | Interquartile range as a percentage of the mean. |
| `_delta_abs` | Absolute range, `max - min`. |
| `_std_perc` | Standard deviation as a percentage of the mean (coefficient of variation expressed in percent). |

## Missing values and zero outcomes

Forty-nine configurations have zero mean throughput and zero mean latency. Percentage statistics that divide by those means are undefined and left blank. The dataset also contains additional blank minimum-percentage fields where a zero minimum prevents the exported relative statistic from being defined consistently. Energy fields are complete for all rows.
