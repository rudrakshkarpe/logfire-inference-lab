# Logfire investigation queries

Paste a query into Logfire's SQL Workbench with a time range covering the workload.
These files use Logfire's documented `records` schema. Verify them against your
project before saving a custom dashboard; the integration tests do not execute
hosted SQL.

- `scenario-latency.sql`: request volume, mean/max duration and failed requests.
- `stages.sql`: queue, prefill and decode durations by scenario.
- `requests.sql`: request-level evidence and trace IDs.

Start with the built-in LLM Tokens and Costs (from records) and Exceptions
dashboards. Fixture token values are workload units, not tokenizer counts.
An unpriced model is not evidence of free inference. Do not infer GPU cost.

For a custom dashboard, use a Table panel for each query initially. Keep server
stage durations and client request latency in separate panels. Do not sum nested
spans or count both SDK and pipeline spans as separate requests.

Reference: https://pydantic.dev/docs/logfire/how-to-guides/write-dashboard-queries/
