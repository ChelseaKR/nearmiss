# Infra — optional, scale-to-zero

nearmiss is designed so an advocacy group with no budget can still run it. The intake can run as a
**stateless, scale-to-zero serverless** function, and the published site is **static-friendly**, so
there is no always-on component to keep paid.

What lives here (optional — the analysis runs entirely offline without any of it):

- A serverless **intake** deploy (validate against the report schema, rate-limit to resist spam and
  poisoning, write to the private raw store).
- A **scheduled rebuild** that re-runs the pipeline and republishes the open dataset, keeping it
  current (timeliness), with rebuild latency budgeted in CI.
- A **container image** and one-command deploy for self-hosting.

Cost target: near zero, with a budget alarm. Secrets are provided via the environment and never
committed — see [`SECURITY.md`](../SECURITY.md).
