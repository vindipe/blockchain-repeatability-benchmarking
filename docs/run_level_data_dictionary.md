# Run-Level Data Dictionary

`dataset/reproducibility-runs.csv` contains 4,105 rows and 26 columns exported
by the benchmark pipeline.

| Column | Meaning |
|---|---|
| `hash` | Technical provenance identifier of the benchmark campaign/export group; it is not an experimental factor. |
| `workload` | Raw workload identifier (`10000`, `dota`, `football`, `gafam`, `paypal`, or `visa`). |
| `run` | Run number within the supplied campaign data; values range from 1 to 10 and are not global replicate identifiers. |
| `mode` | Raw controlled-topology label. The analysis removes a terminal `-l` suffix and maps `full-mesh` to `full mesh`. |
| `dataset` | Workload-source identifier. `diablo` is mapped to `2023`; `our` is mapped to `2024`. |
| `link_strategy` | Network-link strategy; the analysis selects `hop`. |
| `cores` | Allocated CPU cores; the analysis selects 8. |
| `ram` | Allocated RAM in GB; the analysis selects 16. |
| `secondaries` | Configured secondary instances/processes; the analysis selects 10. |
| `network_size` | Raw size code: 1 maps to 10 nodes and 4 maps to 40 nodes. |
| `dynamic` | Dynamic-topology flag; the analysis selects 0. |
| `submit_number` | Number of submitted transactions. |
| `commit_number` | Number of committed transactions. Zero values are preserved. |
| `abort_number` | Number of aborted transactions. |
| `average_load` | Average offered workload reported by the benchmark pipeline. |
| `average_throughput` | Average committed throughput in transactions per second. |
| `average_latency` | Average transaction latency in seconds. |
| `median_latency` | Median transaction latency in seconds. |
| `start_bench` | Benchmark start timestamp. |
| `blockchain` | Raw blockchain identifier (`algorand`, `diem`, `poa`, `quorum`, or `solana`). |
| `MiB-Rx` | Received network traffic in MiB. |
| `MiB-Tx` | Transmitted network traffic in MiB. |
| `energy` | Aggregate energy measurement in kWh exported by the experiment pipeline. |
| `bandwidth` | Raw bandwidth-control field exported with the run. |
| `switch` | Raw switch-control field exported with the run. |
| `latency` | Raw network-latency control field exported with the run. |

## Label mappings used by the script

| Raw value | Analysis label |
|---|---|
| `poa` | Ethereum |
| `diem` | Diem |
| `algorand` | Algorand |
| `solana` | Solana |
| `quorum` | Quorum |
| `dota` | Gaming |
| `football` | FIFA |
| `paypal` | PayPal |
| `visa` | VISA |
| `gafam` | GAFAM |
| `10000` | DDoS |

## Inclusion behavior

The release intentionally preserves the original analysis behavior. After the
fixed experimental filters are applied, the script groups observations by the
configuration fields documented in `methodology.md`. It does not include
`hash` or `run` in the grouping key and does not remove zero-commit rows before
aggregation.

The M1 audit verifies that all `(hash, run)` pairs are unique and that each of
the 1,006 selected campaign hashes is nested in exactly one configuration. Each
configuration contains observations from two to six hashes. Because campaign
hashes can contain partial run sequences, configuration-level `n_observed`
ranges from 9 to 26 even though the within-campaign `run` field ranges from 1 to
10. The hash is retained for auditability, not used to define a treatment or an
evidence level.
