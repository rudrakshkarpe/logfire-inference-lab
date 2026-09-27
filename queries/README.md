# Logfire queries

Paste these SQL statements into Logfire's SQL Workbench. Choose a time window that contains one complete five-scenario run. The CLI prints trace IDs to narrow subsequent investigation.

- `scenario-latency.sql`: count, mean and maximum elapsed request time, and stream failures.
- `stages.sql`: queue, prefill and decode elapsed time in the serving process.
- `requests.sql`: request records with trace IDs and exception types. Returns at most 120 rows.

All three queries were executed against hosted Logfire for the recorded run, using the Query API with an explicit 1,000-row limit and the UTC interval 2026-09-27 06:59:22 to 07:00:00. The service returned 120 request spans and six exceptions. Aggregated results are saved in `docs/evidence/verified-run.json`.

Client and server durations overlap. Do not sum them to estimate end-to-end latency. `duration` in `records` is seconds; these queries convert it to milliseconds. The local CLI summary uses nearest-rank p95, whereas these queries report mean and maximum.

Do not leave the window on all time when comparing runs. That combines repeated experiments, including earlier instrumentation versions. Pending spans are excluded using `duration IS NOT NULL`.
