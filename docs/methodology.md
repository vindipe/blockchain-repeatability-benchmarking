# Methodology and Implemented Analysis

The artifact evaluates repeatability and performance predictability when
blockchain, workload, network topology, and network size are varied under
controlled conditions.

## Inputs

The analysis reads `dataset/reproducibility-runs.csv`. The file contains 4,105
rows from the supplied benchmark export, including campaign identifiers, run
numbers, experimental factors, transaction outcomes, and measured metrics.

The previously published `dataset/reproducibility-dataset.csv` contains the
configuration-level aggregation produced by the same analysis flow.

## Implemented selection

`analysis/plot_reproducibility.py` applies these fixed filters:

```text
dataset       = diablo (mapped to 2023)
link_strategy = hop
secondaries   = 10
cores         = 8
ram           = 16
dynamic       = 0
```

This selects 4,080 observed executions spanning 300
blockchain-topology-workload-size configurations. Configuration-level counts
range from 9 to 26, and only four configurations contain exactly 10
observations. The legacy GAFAM, PayPal, and VISA subset contains 2,053 observed
executions across 150 configurations; only two of those configurations contain
exactly 10 observations.

The raw `hash` column identifies benchmark campaigns. The supplied analysis
groups all selected observations by:

```text
blockchain, mode, workload, cores, ram, secondaries,
dataset, link_strategy, network_size, dynamic
```

It therefore does not use `hash` or `run` as grouping keys. Rows with
`commit_number == 0` are preserved and are not removed before the
configuration-level statistics in the original plotting script. The revised
pipeline retains that script for provenance and implements outcome-state
reconstruction in a separate preprocessing stage.

## Observed-design audit (M1)

`analysis/audit_observed_runs.py` treats each selected CSV row as an observed
execution and reports its configuration and campaign provenance. It verifies
that `(hash, run)` pairs are unique and that every campaign hash is nested in a
single configuration. In the selected corpus, 1,006 campaign hashes contribute
to the 300 configurations, with two to six hashes per configuration.

No complete manifest is available from which a scheduled-attempt count can be
reconstructed. The primary M1 design therefore retains all real observed
executions and reports `n_observed` for every configuration; it does not create
synthetic rows or force a ten-run eligibility rule. The balanced sensitivity
analysis in `analysis/balanced_sensitivity.py` repeatedly samples nine observed
executions per configuration before applying outcome and metric-specific
eligibility masks.

## Observable outcome states and eligibility (M2)

`analysis/derive_run_outcomes.py` classifies each selected row using only the
released transaction counters. The mutually exclusive states are:

- `positive_commit`: `submit_number > 0` and `commit_number > 0`;
- `zero_commit`: `submit_number > 0` and `commit_number == 0`;
- `no_submission`: both counters are zero;
- `inconsistent`: missing, negative, non-integral, or contradictory counters,
  including `commit_number > submit_number`.

No row is labelled as a deployment or execution failure because the released
artifact does not contain the logs required to support that diagnosis. The
selected corpus contains 3,125 positive-commit executions, 953 zero-commit
executions, two no-submission executions, and no inconsistent rows. At
configuration level, 205 cells contain only positive commits, 46 have mixed
outcomes, and 49 contain no positive-commit execution.

Metric validity is separate from outcome classification. TPS and block latency
enter conditional performance distributions only for positive-commit runs;
block latency is structurally undefined when no block is committed. Energy and
network traffic remain valid observed measurements when their stored values are
finite and non-negative, regardless of commit outcome. An additional
positive-commit energy mask supports direct alignment with TPS and latency.
Seven positive-commit rows have stored TPS equal to `0.0`; they remain valid at
the outcome level because TPS is not used to classify a run. Diablo computed
TPS as the committed count divided by its last observed event time, then
printed one decimal place. The released CSV preserves the rounded TPS but not
that last-event time, and the Zenodo archive contains no raw `results.json` from
which it could be recovered. M3 therefore treats these seven TPS measurements
as left-censored (`0 < TPS < 0.05`) and excludes them only from point-valued TPS
statistics. It does not substitute a workload duration, because that would
change Diablo's metric rather than recover its missing precision.

### M3 symmetric dispersion

For every configuration/metric pair, M3 applies one eligibility mask to the
mean, minimum, maximum, quartiles, sample standard deviation, and every derived
deviation. For an eligible value `y` and its configuration mean `m`, the signed
deviation is `y - m` and the signed relative deviation is
`100 * (y - m) / m`. Negative deviations denote observations below the mean;
they are not negative physical measurements. For non-negative observations the
implementation checks the lower bound of `-100%` and the upper bound of
`100(n-1)%`.

The sample standard deviation uses `pandas.Series.std(ddof=1)`, corresponding
to a denominator of `n-1`, and is reported only for `n >= 2`. M3 produces both
all-observed and positive-commit energy views, while TPS and latency use their
positive-commit point-valid masks.

For every configuration, the processed inventory reports `n_observed`,
`n_submitted`, `n_positive_commit`, `n_zero_commit`, `n_no_submission`,
`n_inconsistent`, and metric-specific valid counts. Of the 300 six-workload
configurations, 231 contain at least nine positive-commit runs and can enter the
balanced sensitivity analysis with at least nine positive-commit observations.
The corresponding count is 129 of 150 in the legacy three-workload subset.

### Balanced observed-run sensitivity

`analysis/balanced_sensitivity.py` compares the all-observed primary analysis
with a balanced design based only on released rows. Using seed `20260830`, it
performs 5,000 repetitions. Each repetition samples nine observed executions
from every configuration without replacement. Because sampling is performed
before outcome classification and metric filtering, each configuration has
exactly nine observed rows but may have fewer than nine positive-commit, TPS,
or latency observations. This preserves the distinction between outcome
incidence and conditional performance.

The sensitivity output reports the primary estimate and the median, 2.5th
percentile, and 97.5th percentile across balanced repetitions for
configuration-level statistics, factor-conditioned means and medians, and
dataset-wide extrema. A separate denominator table reports the sampled outcome
and metric-valid counts. The procedure creates no synthetic data and leaves the
released CSV files unchanged.

### Bootstrap uncertainty and generated tables (M4/M7)

`analysis/bootstrap_dispersion_tables.py` quantifies uncertainty in the
configuration-level IQR% and sample-Std% estimates. Its resampling unit is one
metric-eligible observed execution within a fixed configuration. Each
configuration is resampled with replacement at its original metric-specific
count for 5,000 repetitions using seed `20260831`. This differs from the
balanced sensitivity: the bootstrap preserves each cell's observed eligible
count and estimates sampling uncertainty, whereas the balanced analysis draws
nine observed rows to assess design imbalance.

For every bootstrap repetition, configuration-level IQR% and sample-Std% are
aggregated over the remaining factorial dimensions by both the unweighted mean
and the median. The reported 95% intervals are the 2.5th and 97.5th percentiles
of those propagated aggregate estimates. A configuration requires at least two
metric-eligible observations to contribute a dispersion estimate. Every table
row reports the number of contributing configuration cells, their total metric
observations, and the minimum--maximum metric-specific count.

The script produces separate topology-, workload-, and validator-set tables for
TPS, latency, and all-observed energy. It writes one complete set for all six
workloads and a second diagnostic set for the legacy GAFAM/PayPal/VISA subset.
Each `.tex` file is a complete, generated `table*` environment intended for
manuscript inclusion through `\input`; numerical entries are never maintained
manually in the paper source. Machine-readable outputs remain below
`outputs/revision/m4_bootstrap/`, while the manuscript-ready generated tables
are tracked below `paper_tables/` and are deterministically replaced on rerun.

## Metrics and transformations

The script:

- maps raw blockchain, workload, topology, dataset, and size labels to the names
  used in the papers;
- derives committed/submitted-transaction and latency/median-latency ratios;
- treats negative energy values as missing before aggregation;
- computes count, mean, maximum, minimum, 25th percentile, 75th percentile, and
  sample standard deviation for throughput, latency, and energy;
- derives IQR, IQR percentage, minimum and maximum directional percentage
  deviations, absolute range, and standard deviation as a percentage of the
  mean;
- produces blockchain-, topology-, workload-, and scaling-conditioned summary
  tables;
- computes worst-case directional deviations;
- computes a factorial ANOVA over blockchain, topology, workload, size,
  blockchain-topology, and blockchain-workload terms;
- computes an ICC(1,1)-style configuration reliability estimate.

Percentage values requiring a positive denominator are left missing when the
implemented condition is not satisfied.

## Outputs

Running:

```bash
python3 analysis/audit_observed_runs.py
```

creates `outputs/revision/m1_observed_design/audit_summary.json`,
`configuration_inventory.csv`, and `campaign_inventory.csv`. Running:

```bash
python3 analysis/derive_run_outcomes.py
```

creates `outputs/revision/m2_outcomes/run_outcomes.csv`,
`configuration_outcome_counts.csv`, and `outcome_summary.json`. Running:

```bash
python3 analysis/compute_corrected_dispersion.py
```

creates `outputs/revision/m3_dispersion/configuration_metric_statistics.csv`
and `dispersion_summary.json`. Running:

```bash
python3 analysis/balanced_sensitivity.py
```

creates `outputs/revision/balanced_n9/balanced_sensitivity_summary.json` and
the `configuration_sensitivity.csv`, `denominator_sensitivity.csv`,
`factor_sensitivity.csv`, and `extrema_sensitivity.csv` comparison tables.
Running:

```bash
python3 analysis/bootstrap_dispersion_tables.py
```

creates `outputs/revision/m4_bootstrap/bootstrap_summary.json`,
`configuration_bootstrap_intervals.csv`, `factor_bootstrap_summary.csv`, and
standalone LaTeX tables below `paper_tables/six_workloads/` and
`paper_tables/legacy_three_workloads/`. Running:

```bash
python3 analysis/plot_reproducibility.py
```

creates `outputs/reproducibility-dataset.csv`, six LaTeX tables, and twelve
figure variants in both PNG and PDF.

The plots show, for each configuration, the lower and upper signed deviations
derived from the minimum and maximum values in the configuration-level
aggregate. They do not render every observation as an individual point.

## Scope

This artifact reproduces the data-analysis stage from released measurements. It
does not package the complete infrastructure used to deploy blockchains,
emulate networks, execute workloads, or collect raw system measurements.
Consult the papers and the Lilith artifact for that layer.

## Primary references

- ACM article: <https://doi.org/10.1145/3828757>
- Dataset concept DOI: <https://doi.org/10.5281/zenodo.17681717>
- Lilith artifact: <https://doi.org/10.5281/zenodo.11409100>
