"""Client pipeline: ordinary OpenAI SDK streaming over an actual HTTP boundary."""
import asyncio
from time import perf_counter

import logfire
from openai import AsyncOpenAI

from observatory.metrics import Metrics
from observatory.models import RequestResult, Run
from observatory.store import Store
from observatory.telemetry import span, trace_id


async def exercise(run: Run, store: Store, base_url: str):
    metrics = Metrics()
    limiter = asyncio.Semaphore(run.spec.concurrency)
    run.status = "running"
    store.save(run)
    async with AsyncOpenAI(base_url=base_url, api_key="local-workload", max_retries=0,
                           timeout=30) as client:
        logfire.instrument_openai(client, suppress_other_instrumentation=False)
        logfire.instrument_httpx()

        async def request(index: int):
            async with limiter:
                started = perf_counter()
                first = None
                units = 0
                usage = None
                measurements = {}
                error = None
                request_id = f"{run.id}-{index:03d}"
                current_trace = ""
                try:
                    with span("pipeline.request", **{"observatory.run_id": run.id,
                              "observatory.scenario": run.spec.scenario.value,
                              "observatory.request_id": request_id}) as client_span:
                        current_trace = trace_id()
                        stream = await client.chat.completions.create(
                            model="observatory-chat",
                            messages=[{"role": "user", "content": "Explain the evidence for this incident."}],
                            stream=True, stream_options={"include_usage": True},
                            extra_body={"observatory": {"run_id": run.id,
                                "scenario": run.spec.scenario.value, "index": index, "seed": run.spec.seed}},
                        )
                        async with stream:
                            async for chunk in stream:
                                if chunk.choices and chunk.choices[0].delta.content:
                                    units += 1
                                    if first is None:
                                        first = (perf_counter() - started) * 1000
                                        client_span.set_attribute("observatory.first_content_ms", first)
                                if chunk.usage:
                                    usage = chunk.usage
                                measurements.update((chunk.model_extra or {}).get("observatory", {}))
                        if usage is None:
                            raise RuntimeError("Stream completed without its final usage record")
                        if measurements.get("server_trace_id") != current_trace:
                            raise RuntimeError("Trace continuity check failed across the HTTP boundary")
                        client_span.set_attribute("observatory.trace_continuity", True)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    error = type(exc).__name__
                result = RequestResult(
                    request_id=request_id, index=index, status="error" if error else "ok",
                    trace_id=current_trace, duration_ms=(perf_counter()-started)*1000,
                    queue_ms=measurements.get("queue_ms"), prefill_ms=measurements.get("prefill_ms"),
                    first_chunk_ms=first, decode_ms=measurements.get("decode_ms"),
                    input_tokens=usage.prompt_tokens if usage else None,
                    output_tokens=usage.completion_tokens if usage else None,
                    observed_chunks=units, error=error,
                )
                run.results.append(result)
                store.save(run)
                metrics.record(run, result)

        tasks = []
        try:
            with span("workload.run", **{"observatory.run_id": run.id,
                      "observatory.scenario": run.spec.scenario.value,
                      "observatory.requests": run.spec.requests,
                      "observatory.concurrency": run.spec.concurrency}):
                run.trace_id = trace_id()
                tasks = [asyncio.create_task(request(i)) for i in range(run.spec.requests)]
                await asyncio.gather(*tasks)
            run.status = "completed"
        except asyncio.CancelledError:
            run.status = "cancelled"
            raise
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            store.save(run)
