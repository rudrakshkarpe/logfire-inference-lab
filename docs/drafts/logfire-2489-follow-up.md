I followed up with a real GPU run to validate the proposed walkthrough: `google/gemma-4-12B-it` on one H100, served by vLLM 0.30.0 with Logfire 5.1.1 and the OpenAI Python client 3.19.2.

The application passes W3C trace context to vLLM and exports a span covering stream consumption. vLLM exports its native `llm_request` spans over OTLP. I checked the archived spans and read the records back from Logfire:

- All 61 application requests were present, including 56 completed generations, one expected HTTP 400 and four intentional early closures.
- Every completed request had the expected native engine child, with matching parent span ID and input/output token usage.
- The timings distinguished two causes of a slow first response: queue pressure reached 25.38 s p95 engine queue time, while long prompts reached 3.44 s p95 prefill with negligible queueing.

The [lab and reproduction steps](https://github.com/rudrakshkarpe/logfire-inference-lab) include [tested configuration, results and an annotated Logfire walkthrough](https://github.com/rudrakshkarpe/logfire-inference-lab/blob/main/docs/gpu-validation.md), plus a [machine-readable summary](https://github.com/rudrakshkarpe/logfire-inference-lab/blob/main/docs/evidence/gemma4-h100-run.json).

For an upstream guide, I'd keep the example focused on configuring engine export, propagating context, verifying parent links and usage, and interpreting client latency alongside native engine timings. The lab's archive/replay tooling could remain optional. This builds on Logfire's existing OTLP ingestion and AI Inference views.

One boundary worth documenting: the four intentionally closed streams had client records but no native request child in this capture, so I haven't established complete server-side cancellation tracing. The application also uses explicit spans; this run doesn't validate automatic OpenAI streaming error instrumentation. SGLang and TensorRT-LLM would need separate verification.

Would this be a useful scope for a first docs PR, and where would you prefer the walkthrough to live?
