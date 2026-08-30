# Derived Outcome and Eligibility Fields

`analysis/derive_run_outcomes.py` writes a processed run-level file to
`outputs/revision/m2_outcomes/run_outcomes.csv`. The released raw CSV remains
unchanged. Raw factor labels are retained in columns ending in `_raw`, while the
standard factor columns contain the normalized analysis labels.

## Outcome fields

| Field | Definition |
|---|---|
| `outcome_status_derived` | One of `positive_commit`, `zero_commit`, `no_submission`, or `inconsistent`. |
| `submitted_derived` | `True` when a positive number of transactions was submitted and the counters are consistent. |
| `positive_commit_derived` | `True` when both submitted and committed counts are positive. |
| `zero_commit_derived` | `True` when submissions are positive but committed count is zero. |
| `no_submission_derived` | `True` when both submitted and committed counts are zero. |
| `inconsistent_derived` | `True` for missing, negative, non-integral, or contradictory transaction counters. |

These statuses describe only what is observable in the CSV. They do not infer a
deployment or execution failure from the absence of committed transactions.

## Metric-validity fields

| Field | Definition |
|---|---|
| `tps_valid_positive_commit` | Positive-commit outcome and finite, non-negative stored TPS. A stored `0.0` is retained pending the full-precision M3 recomputation. |
| `latency_valid_positive_commit` | Positive-commit outcome and finite, strictly positive average block latency. |
| `energy_valid_observed` | Finite, non-negative energy measurement, independent of commit outcome. |
| `energy_valid_positive_commit` | `energy_valid_observed` restricted to positive-commit outcomes. |
| `network_valid_observed` | Finite, non-negative received and transmitted network measurements, independent of commit outcome. |

## Configuration inventory

`configuration_outcome_counts.csv` reports, for every configuration:

- `n_observed`;
- `n_submitted`;
- `n_positive_commit`;
- `n_zero_commit`;
- `n_no_submission`;
- `n_inconsistent`;
- the valid count for each metric mask;
- `service_regime_derived`, with values `all_positive_commit`,
  `mixed_outcomes`, or `no_positive_commit`.

The term `failed` is intentionally absent. Establishing a technical failure
would require deployment or execution logs that are not part of the released
artifact.
