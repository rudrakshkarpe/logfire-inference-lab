# Proposed upstream guide outline

Working title: **Trace an application request through a self-hosted inference service**

Target: [pydantic/logfire#2489](https://github.com/pydantic/logfire/issues/2489). This is a proposed documentation structure, not a claim that a docs PR has been submitted or accepted.

## Problem

An application can report a slow first token without showing whether the delay came from server queueing or model prefill. Developers need a worked example that combines existing Logfire model telemetry with native engine measurements and verifies the relationship between them.

## Walkthrough

1. **Set up a tested configuration.** List client and engine versions, GPU requirements, model revision, context limit and tracing flags. Use the verified vLLM configuration as the first example.
2. **Export native engine spans.** Configure OTLP ingestion with the correct regional endpoint and authentication. Explain service names and keep credentials outside source code. The lab's receiver/SSH path is verified; a simpler direct-export recipe needs its own validation before inclusion.
3. **Follow one streamed request.** Keep an application span open through consumption, inject `traceparent`, and find the native `llm_request` child. Explain the chosen explicit instrumentation and avoid adding duplicate automatic model instrumentation.
4. **Verify the records.** Check the parent span ID, final usage and hosted ingestion. Explain why matching trace IDs or a successful exporter flush alone are insufficient.
5. **Diagnose a delayed first response.** Compare queue pressure with a long prompt using native engine queue/prefill attributes. State units and distinguish client network timing from engine statistics.
6. **Show the boundaries.** Include the pre-generation HTTP 400 and the observed early-closure limitation. Keep missing usage absent. State that other engines and automatic streaming error handling need separate tests.

## Evidence available for review

- [Configuration, workload and screenshots](../gpu-validation.md).
- [Machine-readable measurements and trace IDs](../evidence/gemma4-h100-run.json).
- [Capture, verification and replay scripts](../../scripts/gpu/README.md).

The strongest example is a request with 23.046 s of native queue wait, 53 ms of prefill and 6.108 s of decode. The linked screenshot shows the actual attributes and application parent. This demonstrates a practical diagnostic workflow without needing a custom dashboard.

## Keep outside the first guide

Archive/replay mechanics, Runpod account setup and comparative engine benchmarks can stay in the reference lab. Do not claim SGLang or TensorRT-LLM support until each has been tested. Do not treat the absence of cancellation spans as a confirmed Logfire bug without isolating the engine's behavior.

## Before opening a docs PR

Confirm the maintainer's preferred location and scope. Adapt the runnable example to the documentation conventions, validate any changed export route, and pin evidence links to the published lab revision. Keep the engine-independent explanation separate from version-specific flags.
