-- Table or bar-chart source. Never mix client duration with nested server spans.
SELECT attributes->>'observatory.scenario' AS scenario,
       COUNT(*) AS requests,
       AVG(duration) * 1000 AS mean_request_ms,
       MAX(duration) * 1000 AS max_request_ms,
       SUM(CASE WHEN is_exception THEN 1 ELSE 0 END) AS failed_requests
FROM records
WHERE service_name = 'inference-application'
  AND span_name = 'pipeline.request'
  AND duration IS NOT NULL
GROUP BY scenario
ORDER BY scenario
