# Run-Level Data Dictionary

`dataset/reproducibility-runs.csv` contains 4,105 rows and 26 columns exported
by the benchmark pipeline.

| Column | Meaning |
|---|---|
| `hash` | Technical provenance identifier of the benchmark campaign/export group; it is not an experimental factor. |
| `workload` | Raw workload identifier (`10000`, `dota`, `football`, `gafam`, `paypal`, or `visa`). |
| `run` | Run number within the supplied campaign data; values range from 1 to 10 and are not global replicate identifiers. |
| `mode` | Raw controlled-topology label. The analysis removes a terminal `-l` suffix and maps `full-mesh` to `full mesh`. |
| `dataset` | Network-trace identifier. `diablo` is mapped to the 2023 RTT-trace vintage; `our` is mapped to 2024. It is not a campaign execution year. |
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
| `average_throughput` | Average committed throughput in transactions per second exported by Diablo with one decimal place. A stored zero with `commit_number > 0` is a left-censored positive TPS, not a true zero-throughput outcome. |
| `average_latency` | Average transaction latency in seconds. |
| `median_latency` | Median transaction latency in seconds. |
| `start_bench` | Benchmark execution start timestamp. In the selected corpus it ranges from 21 April 2024 to 8 August 2025; it is distinct from the 2023 RTT-trace vintage. |
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

Outcome states and metric-specific validity are not encoded in the raw file.
They are added by `analysis/derive_run_outcomes.py` to a separate processed
output documented in
[`derived_outcome_data_dictionary.md`](derived_outcome_data_dictionary.md).

## Network-trace and campaign-time provenance

Every row selected for the manuscript has raw `dataset=diablo`. The analysis
label `2023` identifies the replayed AWS RTT trace vintage, not the year in
which the benchmark ran. The frozen trace input is Lilith
`misc/diablo-aws.csv` at commit
`dd1d457c6079661b158f601cdf70817cbe2a5f2a`, SHA-256
`c7f384cf276666293d275d4c5056dface1d6271f54e449fd9629024b7ab1b7d3`.
The source records the 2023 vintage but not an exact collection day.

`start_bench` independently records campaign execution time. The 4,080
selected rows range from `2024-04-21 21:29:22.775` to
`2025-08-08 17:05:23.621`. These fields and their non-equivalence are frozen in
`outputs/revision/m1_observed_design/audit_summary.json`.
