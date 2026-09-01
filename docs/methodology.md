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
exactly 10 observations. The complete six-workload corpus is the primary
manuscript scope; the three-workload subset is retained only for compatibility
and sensitivity checks.

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

## GAFAM workload trace audit (m2)

The raw workload label `gafam` maps to the manuscript label `GAFAM` and selects
`inputs/workloads/workload-gafam-long.yaml`. The YAML trace uses seconds as
keys and offered TPS as values. It defines control points of 19,800 TPS at
second 0 and 115 TPS at second 1, then control points spanning 25--140 TPS
through second 180, followed by 37 TPS at second 180 and zero at second 300.
Diablo linearly interpolates between successive control points; the 19,800-TPS
value is therefore not a three-minute constant plateau.

`analysis/audit_gafam_trace.py` checks the filename, packaged and upstream
SHA-256 values, 300-second duration, units, trace identifier, contract selector,
and schedule. It also verifies the corpus-side link: all 668 selected GAFAM
observations originate from raw label `gafam`, report 30,320 submitted
transactions, and retain recorded average-load values of 167.6 or 167.7 TPS.
The machine-readable audit and control-point schedule are written to
`outputs/revision/m2_gafam_trace/`.

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

### Two-part factorial models and ICC (S1--S3/R2.4)

`analysis/fit_two_part_models.py` separates outcome incidence from conditional
performance. The outcome component is a binomial GLM for
`positive_commit_derived`. The conditional component fits natural-log TPS,
latency, and energy using the corresponding positive-service validity mask.
Each primary model includes blockchain, topology, workload, validator-set size,
and all six two-way interactions.

For the outcome model, interaction terms use likelihood-ratio deletion tests.
A main factor cannot be removed while retaining interactions containing that
factor without violating model hierarchy; each main-factor result is therefore
a hierarchical omnibus likelihood-ratio test of that factor and all its
interactions. Complete or quasi-complete separation is checked and reported.
When the diagnostic flags quasi-separation, the outcome likelihood-ratio rows
are treated as model-screening evidence for service incidence rather than
finite-sample causal inference.
For conditional log-performance, primary inference uses Type-II tests with HC3
heteroscedasticity-robust covariance. Classical sums of squares are used only
to derive partial eta squared. Type-III HC3 tests under sum-to-zero contrasts
are retained as a sensitivity. Residual-versus-fitted and Q--Q plots,
Breusch--Pagan statistics, and Jarque--Bera statistics are written with the
machine-readable term tables.

The script verifies design-matrix rank before inference. All legacy
three-workload two-way models and both targeted three-way additions are full
rank. The six-workload outcome model is also full rank. Conditional on positive
service, however, Quorum has no FIFA or Gaming observations and only one DDoS
observation. The nominal two-way design is consequently rank-deficient by two.
Rather than suppressing every conditional test or fitting a pseudoinverse as if
all coefficients were estimable, the implementation constructs a deterministic
full-rank basis spanning the complete observed-support column space. Primary
HC3 Type-II and Type-III sensitivity tests are then computed as joint
restrictions under the fixed sum-contrast specification. The
blockchain--workload interaction has 18 supported degrees of freedom rather
than 20; both values and the empty cells are written to the audit output, and
no observation is imputed.

Targeted three-way additions use the same rule. The artifact reports
likelihood-ratio tests for the full-rank outcome component and HC3 tests over
the rank added by each conditional interaction. Where empty positive-service
cells reduce nominal rank, the generated table states ``reported on observed
support'' and prints supported rank over nominal columns.

`analysis/icc_by_blockchain.py` fits a separate intercept-only REML mixed model
for each blockchain and metric on the natural-log scale, with configuration as
the random intercept. It reports between-configuration variance,
within-configuration variance, and
`ICC = between / (between + within)`. Uncertainty is quantified by resampling
complete configuration clusters with replacement, relabelling duplicated
clusters, refitting the model, and taking the 2.5th and 97.5th percentiles of
1,000 deterministic bootstrap replicates (base seed `20260901`). The pooled
global raw-scale ICC is not used as evidence of repeatability.
The script can also rebuild the LaTeX tables from a completed machine-readable
ICC CSV without refitting; each scope reports the first seed used by its own
deterministic bootstrap stream.

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
python3 analysis/fit_two_part_models.py
```

creates term-level outcome and conditional-performance tests, Type-III
sensitivities, targeted three-way sensitivity tests, design-rank audits,
residual diagnostics, and generated model tables below
`outputs/revision/statistical_models/` and `paper_tables/`.
Running:

```bash
python3 analysis/icc_by_blockchain.py
```

creates the within-blockchain variance-component and ICC table, bootstrap
intervals, and generated LaTeX tables below
`outputs/revision/icc_by_blockchain/` and `paper_tables/`. Running:

```bash
python3 analysis/audit_gafam_trace.py
python3 analysis/workload_catalog.py
python3 analysis/plot_run_level_deviations.py
```

creates the m2 GAFAM trace audit, the six-workload catalog under
`outputs/revision/m1_workloads/`, its generated LaTeX table under
`paper_tables/six_workloads/`, and twelve corrected
PDF run-level deviation figures under `outputs/revision/m1_figures/`.
Running the legacy provenance script separately:

```bash
python3 analysis/plot_reproducibility.py
```

creates `outputs/reproducibility-dataset.csv`, six LaTeX tables, and twelve
figure variants in both PNG and PDF.

The plots render every metric-eligible execution as an individual circular
marker at its signed absolute and relative deviation from the corresponding
configuration mean. A deterministic horizontal offset in the interval
`[-0.18, 0.18]` separates executions that belong to the same configuration;
it has no statistical meaning and does not change factor assignment. The
generated `plotted_execution_manifest.csv` provides a row-by-row audit from
the source execution identifiers to every plotted coordinate.

## M6 hash-batch audit

The `hash` field identifies an execution batch nested within exactly one
blockchain--topology--workload--size configuration. The `run` index is reused
across configurations and restarts within hash batches, while `dataset` is
constant in the selected corpus. These columns therefore do not define a
campaign factor crossed with configuration. The M6 audit preserves the pooled
configuration-level analysis and adds a descriptive sums-of-squares
partitioning into within-hash and between-hash components. Its strict
sensitivity subset requires at least two hash batches that each contain at
least two metric-eligible executions. This partition is reported as a
sensitivity to collection-batch boundaries, not as an independently identified
campaign variance component.

## Scope

This artifact reproduces the data-analysis stage from released measurements. It
does not package the complete infrastructure used to deploy blockchains,
emulate networks, execute workloads, or collect raw system measurements.
Consult the papers and the Lilith artifact for that layer.

## Primary references

- ACM article: <https://doi.org/10.1145/3828757>
- Dataset concept DOI: <https://doi.org/10.5281/zenodo.17681717>
- Lilith artifact: <https://doi.org/10.5281/zenodo.11409100>
