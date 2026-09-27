import asyncio
from time import perf_counter

import logfire

from observatory.models import RequestResult, Run
from observatory.scenarios import PROFILES, timing
from observatory.telemetry import span, trace_id


class StreamInterrupted(Exception):
    """An intentional, repeatable interruption of the workload stream."""


async def execute_request(run: Run, index: int, slots: asyncio.Semaphore) -> RequestResult:
    profile = PROFILES[run.spec.scenario]
    prefill_target, chunk_target = timing(run.spec.seed, index, profile)
    request_id = f"{run.id}-{index:03d}"
    queue_ms = prefill_ms = decode_ms = 0.0
    first_chunk_ms = None
    output_tokens = 0
    error = None
    started = perf_counter()
    attrs = {
        "observatory.run_id": run.id,
        "observatory.scenario": run.spec.scenario.value,
        "observatory.request_id": request_id,
        "gen_ai.system": "observatory",
        "gen_ai.provider.name": "observatory",
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": "observatory-chat",
        "gen_ai.response.model": "observatory-chat",
        "observatory.token_basis": "generated-workload-units",
    }
    with span("inference.request", **attrs) as request_span:
        current_trace = trace_id()
        acquired = False
        try:
            queued = perf_counter()
            with span("queue.wait", **{"observatory.request_id": request_id}):
                await slots.acquire()
                acquired = True
            queue_ms = (perf_counter() - queued) * 1000
            prefill_started = perf_counter()
            with span("model.prefill", **{"observatory.request_id": request_id}):
                await asyncio.sleep(prefill_target / 1000)
            prefill_ms = (perf_counter() - prefill_started) * 1000
            decode_started = perf_counter()
            try:
                with span("model.decode", **{"observatory.request_id": request_id}):
                    for chunk in range(profile.chunks):
                        await asyncio.sleep(chunk_target / 1000)
                        output_tokens += 1
                        if first_chunk_ms is None:
                            first_chunk_ms = (perf_counter() - started) * 1000
                            request_span.set_attribute(
                                "gen_ai.client.operation.time_to_first_chunk", first_chunk_ms / 1000
                            )
                        if (
                            profile.fail_every
                            and (index + 1) % profile.fail_every == 0
                            and chunk == 5
                        ):
                            raise StreamInterrupted("Stream ended before its final usage chunk")
            finally:
                decode_ms = (perf_counter() - decode_started) * 1000
        except StreamInterrupted as exc:
            error = str(exc)
            request_span.set_level("error")
            request_span.set_attribute("error.type", "StreamInterrupted")
            logfire.error(
                "Stream interrupted after {chunks} chunks",
                chunks=output_tokens,
                **{"observatory.run_id": run.id},
            )
        finally:
            if acquired:
                slots.release()
        request_span.set_attribute("gen_ai.usage.input_tokens", 128)
        request_span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        request_span.set_attribute("gen_ai.response.finish_reasons", ["error" if error else "stop"])
        request_span.set_attribute("observatory.queue_ms", queue_ms)
        request_span.set_attribute("observatory.prefill_ms", prefill_ms)
        request_span.set_attribute("observatory.decode_ms", decode_ms)
        request_span.set_attribute("observatory.status", "error" if error else "ok")
    return RequestResult(
        request_id=request_id,
        index=index,
        status="error" if error else "ok",
        trace_id=current_trace,
        duration_ms=(perf_counter() - started) * 1000,
        queue_ms=queue_ms,
        prefill_ms=prefill_ms,
        first_chunk_ms=first_chunk_ms,
        decode_ms=decode_ms,
        input_tokens=128,
        output_tokens=output_tokens,
        error=error,
    )
