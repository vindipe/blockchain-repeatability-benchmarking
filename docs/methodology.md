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
configuration-level statistics are computed. This release documents and
reproduces that behavior without adding a new campaign-selection manifest or
new outcome-state reconstruction.

## Observed-design audit (M1)

`analysis/audit_observed_runs.py` treats each selected CSV row as an observed
execution and reports its configuration and campaign provenance. It verifies
that `(hash, run)` pairs are unique and that every campaign hash is nested in a
single configuration. In the selected corpus, 1,006 campaign hashes contribute
to the 300 configurations, with two to six hashes per configuration.

No complete manifest is available from which a scheduled-attempt count can be
reconstructed. The primary M1 design therefore retains all real observed
executions and reports `n_observed` for every configuration; it does not create
synthetic rows or force a ten-run eligibility rule. A later balanced sensitivity
analysis will repeatedly sample nine eligible real runs per configuration after
the metric-specific eligibility masks are defined. That later step is outside
M1 and is intentionally not implemented by this audit.

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
