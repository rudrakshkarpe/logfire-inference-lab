# Logfire Inference Lab

**Trace a streamed model request from an application into the inference engine, then diagnose it in Pydantic Logfire.**

This project connects an OpenAI-compatible client to a self-hosted model, carries trace context across the serving boundary, and verifies the resulting records in Logfire. The GPU capture uses **Gemma 4 12B, vLLM 0.30.0 and one H100 80GB**. A separate laptop fixture makes streaming failures and timing scenarios reproducible without a GPU. Logfire provides the investigation UI.

![Real Gemma inference in Logfire: model totals, trace links and native engine timings](docs/assets/logfire-gemma-walkthrough.gif)

*A 10.8-second edited walkthrough of actual Logfire screenshots, with zoomed excerpts and highlights. [Static dashboard](docs/assets/logfire-gemma-model.png) · [Image provenance](docs/assets/README.md#gemma-h100-capture). The dashboard includes 61 main requests plus two smoke requests; its one exception is deliberate. Four intentional early closures appear as successful client spans, not completed generations.*

## What the GPU run verified

The main run on September 27, 2026 sent **61 requests**: 56 completed generations, one expected HTTP 400 and four intentionally closed streams. A separate hosted SQL query found every application record and **all 56 expected native engine children**, checking exact parent span IDs. Input and output token counts matched between each completed response and its engine span.

The completed main requests used **53,742 input tokens** and produced **11,264 output tokens**. Original OTLP batches, request/response chunks, Prometheus snapshots, GPU samples and version information are preserved in a checksum-verified local archive. Public summaries and screenshots are included here.

| Scenario | Requests | Client concurrency | Output limit | p95 client first content | p95 engine queue | p95 engine prefill |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 8 | 1 | 128 | 0.282 s | 0.053 ms | 57.48 ms |
| Queue pressure | 32 | 16 | 256 | 25.681 s | 25.379 s | 76.48 ms |
| Long context | 8 | 2 | 128 | 3.977 s | 0.056 ms | 3.444 s |
| Recovery | 8 | 1 | 128 | 0.254 s | 0.058 ms | 52.72 ms |

These are nearest-rank percentiles from a short diagnostic workload. Client timing includes SSH and network transport; queue and prefill timing come from vLLM. The engine schedules at most four sequences. Queue pressure changes both concurrency and output length, while long-context prompts contain about 6,400 tokens. This configuration uses eager execution, detailed tracing and no prefix caching. It is not a throughput benchmark.

[Exact results and trace IDs](docs/evidence/gemma4-h100-run.json) · [Full validation report](docs/gpu-validation.md)

## From a slow response to its cause

![Native vLLM request span with queue, prefill and decode timings](docs/assets/logfire-gemma-native-queue.png)

The selected request took **29.218 seconds** inside vLLM: **23.046 seconds waiting in the queue**, **53 ms in prefill**, and **6.108 seconds in decode**. Its application parent is visible in the same trace. Engine timing makes the cause of the slow first response explicit.

The long-context scenario shows a different pattern: p95 prefill rises to **3.444 seconds** while queue wait remains below **0.06 ms**. Recovery returns to the baseline prompt/output sizes and client concurrency, bringing p95 first-content time back to **254 ms**.

The guide covers how to read those measurements, verify ingestion, and preserve missing usage instead of estimating it. Native prefill and decode values are engine request statistics, not GPU kernel profiles.

## How the real-engine integration works

```text
Application process                         vLLM serving process
  gpu.workload
    chat google/gemma-4-12B-it --traceparent--> llm_request
              |                                  |
              | OTLP/HTTP                         | OTLP/HTTP
              v                                  v
                   Local archive receiver
                     |-- original protobuf + checksums
                     `-- authenticated forwarding --> Logfire
```

The application keeps one explicit GenAI span open through stream consumption and injects W3C `traceparent` into each request. vLLM's native instrumentation extracts that context and records queue, prefill, decode and token usage. Separate service names identify the application and engine.

SSH forwards carry inference traffic and engine telemetry between loopback endpoints. The archive receiver preserves each protobuf batch before forwarding it to Logfire. Credentials remain on the laptop. Hosted SQL verification checks actual records and parent links after export.

This path uses Python, the OpenAI client, Logfire and OpenTelemetry with vLLM's serving layer. The separate laptop fixture adds a Pydantic/FastAPI backend. The `openai` label in Logfire identifies the compatible API convention; the captured model ran on the H100.

## Run either path

Start with Python 3.11 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
git clone https://github.com/rudrakshkarpe/logfire-inference-lab.git
cd logfire-inference-lab
uv sync --locked --no-editable
```

| Path | Requirements | Instructions |
|---|---|---|
| Real inference | Compatible GPU host, model storage, SSH and a Logfire project | [GPU capture setup](scripts/gpu/README.md#reproduce-the-gpu-capture) |
| Laptop fixture | Local Python environment; Logfire export optional | [Laptop walkthrough](docs/laptop-lab.md) |
| Replay saved traces | An existing OTLP archive and a chosen receiver | [Replay instructions](scripts/gpu/README.md#replay-on-another-platform) |

The GPU launch pins model revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`, uses BF16 text-only inference and an 8,192-token context. The capture tools preserve workload inputs, streamed chunks, token usage and errors. Verification requires a matching native engine child for every completed request.

Replay was tested locally across **91 batches containing 178 spans**, including startup telemetry. It preserved relationships, events, durations and attributes while shifting timestamps and assigning new trace IDs. Dash0 ingestion has not been tested. Prometheus snapshots and GPU CSV remain separate evidence; replaying traces does not rerun inference.

## Scope and known limits

- **Validated:** vLLM 0.30.0 with `google/gemma-4-12B-it` on one H100; Chat Completions streaming, native trace continuity and completed-request usage.
- **Invalid request:** asking for 9,000 output tokens exceeds the configured context. The SDK raises `BadRequestError`, which the application span records. This tests rejection before generation.
- **Early closure:** four clients close after five content chunks. Final usage stays null. No native request child was observed for these calls, so the capture does not establish complete engine cancellation tracing.
- **Instrumentation:** this run uses explicit application spans. It does not validate automatic `logfire.instrument_openai()` streaming error handling.
- **Other engines:** SGLang, TensorRT-LLM, multimodal input and other model/version combinations remain untested.

The laptop fixture separately exercises errors after streaming has begun. Its [120-request result](docs/laptop-lab.md#recorded-fixture-result) and [animated walkthrough](docs/assets/logfire-walkthrough-zoom.gif) are retained with their own provenance.

## Development and documentation

```bash
make lint
make test
make gpu-gif  # Rebuild the real-engine walkthrough from its source PNGs.
```

The local suite has 26 tests: 14 cover the fixture's client/server behavior, trace parents, failures and timing signatures; 12 cover archive integrity, forwarding responses, usage coverage and workload completeness. GPU validation additionally checks archived spans, returned usage and hosted records. See the [fixture integration guide](docs/integration.md), [telemetry contract](docs/telemetry.md) and [operations guide](docs/operations.md).

A proposed upstream walkthrough is tracked in [pydantic/logfire#2489](https://github.com/pydantic/logfire/issues/2489). Local [maintainer follow-up drafts](docs/drafts/README.md) collect the verified findings and a suggested documentation scope for later review.

MIT licensed.
