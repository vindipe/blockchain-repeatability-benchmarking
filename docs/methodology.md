# Methodology Notes

The study evaluates whether repeated blockchain benchmarks produce stable results when the application workload is held constant and the network topology and network size are controlled.

## Experimental factors

The released matrix varies four primary factors:

1. blockchain implementation;
2. network topology;
3. workload;
4. network size.

The experiments use Lilith to combine blockchain workload generation with controlled network deployment/emulation. This makes it possible to change the underlying topology without changing the blockchain application logic.

## Outcome families

The public CSV exposes aggregate statistics for:

- throughput;
- latency;
- energy consumption;
- committed transactions.

Repeatability is represented through run counts, extrema, quartiles, standard deviations, absolute ranges, and relative-dispersion measures. These fields make it possible to identify configurations whose averages appear acceptable but whose repeated executions are unstable.

## Interpretation cautions

- The CSV is configuration-level aggregate data, not a run-level trace archive.
- A zero throughput/latency outcome makes percentage-of-mean dispersion undefined; blank relative fields must not be silently converted to zero.
- Comparisons should preserve the workload and network-size context, since both can materially change the observed behavior.
- The public plotting utility averages or takes medians across selected factors for exploration. Consult the paper for the formal statistical analysis, factor attribution, predictability taxonomy, and result interpretation.

## Primary references

- Article: <https://doi.org/10.1145/3828757>
- Dataset: <https://doi.org/10.5281/zenodo.17681717>
- Lilith artifact: <https://doi.org/10.5281/zenodo.11409100>
