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
