# Workload inputs

`workload-gafam-long.yaml` is the GAFAM workload definition selected by the
Lilith execution loop for the raw workload label `gafam`. It is mirrored from
`vindipe/lilith` commit `dd1d457c6079661b158f601cdf70817cbe2a5f2a`, path
`kollaps/examples/diablo/primary/fixes/workload-gafam-long.yaml`.

The trace uses seconds as keys and offered transactions per second (TPS) as
values. Diablo expands the control points by linear interpolation. The source
file SHA-256 is
`11fd627b4fba15884605b1fda1e11d701b10538b9f1ccf9e61fd458e2aff17ba`.
This mirror adds one terminating LF, without changing the YAML content, and has
SHA-256
`11d4fb66ef30608764bb91ee8fb62ecddc294c6d19fc2d8ba7cd9e71d7ce83b7`.
Both values are recorded by `analysis/audit_gafam_trace.py`.

## PayPal and Gaming

The pinned [Lilith runner][runner] selects `paypal` and `dota` and constructs
the corresponding YAML filenames. It leaves the `paypal-long` selector
commented out.

- **PayPal.** The runner selects [`workload-paypal.yaml`][paypal], with
  control points of 200 TPS at 0 seconds and zero at 300 seconds.
  All 688 selected runs submitted 59,990 transactions each and record
  an offered load of 199.9 or 200.0 TPS.
- **Gaming.** The released [`workload-dota.yaml`][dota] defines a
  `dota:update` profile with nonzero control points between 2,000 and
  2,500 TPS. The observed run dataset records 3,678,700 submissions per
  submitting Gaming run and a median offered load of 13,328.2 TPS. The
  release file documents the workload name and contract. Its rate schedule
  differs from the campaign measurements, so the paper reports the recorded
  offered load. [Run-level dataset](../../dataset/reproducibility-runs.csv) ·
  [Offered-load audit](../../outputs/revision/r3_9_offered_load/by_workload.csv)

[runner]: https://github.com/vindipe/lilith/blob/dd1d457c6079661b158f601cdf70817cbe2a5f2a/kollaps/examples/diablo/primary/minion.sh#L49-L81
[paypal]: https://github.com/vindipe/lilith/blob/dd1d457c6079661b158f601cdf70817cbe2a5f2a/kollaps/examples/diablo/primary/fixes/workload-paypal.yaml
[dota]: https://github.com/vindipe/lilith/blob/dd1d457c6079661b158f601cdf70817cbe2a5f2a/kollaps/examples/diablo/primary/fixes/workload-dota.yaml
