# Telemetry contract

The source of every manual span is `observatory.source=synthetic` and `observatory.engine=workload-model`. These are also resource attributes. The recorded values are real wall-clock measurements of the fixture; they do not describe GPU inference performance.

## Span and measurement boundaries

| Field or span | Unit | Meaning |
|---|---|---|
| `pipeline.request` duration | seconds in Logfire | Client request creation through complete stream consumption or error |
| `inference.serve` duration | seconds | Server generator lifetime, including admission and streamed response |
| `queue.wait` | seconds | Server wait for a semaphore slot |
| `model.prefill` | seconds | Server preparation stage after admission |
| `model.decode` | seconds | Server streamed content stage, including asynchronous send/backpressure effects |
| `gen_ai.client.operation.time_to_first_chunk` | seconds | Client elapsed time to first parsed protocol chunk |
| `observatory.first_content_ms` | milliseconds | Client elapsed time to first nonempty content delta |
| CLI `p95_first_chunk_ms` | milliseconds | Historical field name: p95 of first **content** time, not any protocol chunk |
| `gen_ai.usage.input_tokens` | fixture units | Final server-reported prompt count, fixed at 128 |
| `gen_ai.usage.output_tokens` | fixture units | Final server-reported content chunk count |
| `observed_chunks` in SQLite | chunks | Content chunks actually seen, including partial responses |
| `observatory.trace_continuity` | boolean | Final server trace ID matched the client trace ID |

The first chunk in this fixture also contains content, so the two first-response timers are close. A real engine may first send only a role or metadata record. Preserve that distinction when adapting the client.

Server span durations and returned stage measurements have slightly different timer placement and instrumentation overhead. They should be comparable, not byte-for-byte identical. Client and server clocks are used only for local elapsed time; subtracting timestamps across machines would be unsafe.

## Missing usage and failure semantics

An interrupted stream supplies no final usage record. Its input/output token counts and returned server stage measurements remain `null` in the local result. The trace still contains measured server stages and the client records the six observed content chunks. Aggregated usage includes only 114 successfully completed calls in the recorded 120-request run.

A failed server stream emits a structured error event and marks the serving span at error level. The SDK client raises an exception, so `records.is_exception` is true on the application request. Queries count exceptions on `pipeline.request`, avoiding duplicate counting of the same failure in different layers.

The built-in UI calls the first-response measurement "Time to first token" and displays token speed. For this fixture those are protocol-chunk timing and fixture-unit throughput. Cost is unavailable because `observatory-stream` has no pricing data. No GPU utilization, cache hit rate or model quality is measured.

## Metrics

| Instrument | Type | Unit |
|---|---|---|
| `observatory.request.duration` | Histogram | seconds |
| `observatory.client.first_content` | Histogram | seconds |
| `observatory.queue.duration` | Histogram | seconds |
| `observatory.requests` | Counter | requests |

Labels are scenario, model, source and status. Run IDs and request IDs stay on spans, avoiding unbounded metric cardinality. The screenshots and hosted verification use span records; this report does not claim a separate validation of every exported histogram bucket.

## Persistence and privacy

`data/observatory.db` stores run configuration, measurements and result status. `data/*-spans.jsonl` stores IDs, timings and an allowlist of workload/usage attributes for local structural checks. Both paths are ignored by Git. The exporter never writes prompts or headers to JSONL. The demo uses a fixed non-sensitive prompt. Do not substitute confidential prompts without reviewing the SDK's capture/scrubbing configuration and your project's access controls.

Run the CLI sequentially against one database. Opening a new `Store` marks unfinished runs as interrupted after a prior process exit; it is not a multi-process job scheduler. Server pools are process-local, so multiple serving workers would each have independent admission capacity.

Environment files and `.logfire/` credentials are ignored and excluded from the Docker build context. The container does not inherit host CLI credentials. Supply a project write token through its environment if you enable export there. A read token is optional and is only used by the separate verification command.
