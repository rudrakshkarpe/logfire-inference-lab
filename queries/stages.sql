-- Logfire SQL Workbench: elapsed server time by stage and scenario.
-- Set a time range covering your demo. Each row is one completed stage span.
SELECT
    attributes->>'observatory.scenario' AS scenario,
    span_name AS stage,
    COUNT(*) AS requests,
    AVG(duration) * 1000 AS mean_ms,
    MAX(duration) * 1000 AS max_ms
FROM records
WHERE service_name = 'inference-serving'
  AND span_name IN ('queue.wait', 'model.prefill', 'model.decode')
  AND duration IS NOT NULL
GROUP BY scenario, stage
ORDER BY scenario, stage
