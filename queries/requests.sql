-- One row per client pipeline request, including streaming failures.
SELECT start_timestamp, trace_id,
       attributes->>'observatory.run_id' AS run_id,
       attributes->>'observatory.scenario' AS scenario,
       duration * 1000 AS duration_ms,
       attributes->>'observatory.first_content_ms' AS first_content_ms,
       is_exception, exception_type
FROM records
WHERE service_name = 'inference-application'
  AND span_name = 'pipeline.request'
  AND duration IS NOT NULL
ORDER BY start_timestamp DESC
LIMIT 120
