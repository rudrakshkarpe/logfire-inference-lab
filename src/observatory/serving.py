"""OpenAI-compatible fixture service with real HTTP streaming and measured stages."""
import asyncio
import json
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from time import perf_counter

import logfire
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from observatory.models import Scenario
from observatory.scenarios import PROFILES, timing
from observatory.settings import Settings
from observatory.telemetry import configure, flush, span, trace_id


class WorkloadOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field("manual", pattern=r"^[a-zA-Z0-9-]{1,40}$")
    scenario: Scenario = Scenario.baseline
    index: int = Field(0, ge=0, le=100000)
    seed: int = Field(42, ge=0, le=2**31-1)


class ChatRequest(BaseModel):
    model: str = "observatory-chat"
    messages: list[dict] = Field(min_length=1, max_length=20)
    stream: bool = True
    observatory: WorkloadOptions = Field(default_factory=WorkloadOptions)


def create_serving_app(settings: Settings | None = None, *, instrument: bool = True):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        if instrument:
            configure(settings, service_name="inference-serving")
        yield
        if instrument:
            await asyncio.to_thread(flush)

    app = FastAPI(title="Inference serving fixture", lifespan=lifespan)
    pools = OrderedDict()
    if instrument:
        logfire.instrument_fastapi(app, capture_headers=False, excluded_urls="/health")

    @app.get("/health")
    def health():
        return {"status": "ok", "source": "synthetic", "engine": "workload-model"}

    @app.get("/v1/models")
    def models():
        return {"object": "list", "data": [{"id": "observatory-chat", "object": "model",
                                           "created": 0, "owned_by": "observatory"}]}

    @app.post("/v1/chat/completions")
    async def completion(body: ChatRequest):
        if not body.stream:
            raise HTTPException(400, "This lab exercises streaming requests; set stream=true")
        if body.model != "observatory-chat":
            raise HTTPException(404, "Unknown fixture model")
        options = body.observatory
        profile = PROFILES[options.scenario]
        key = (options.run_id, options.scenario)
        if key not in pools:
            # Bound memory without evicting pools whose requests are still in flight.
            if len(pools) >= 128:
                stale = next((k for k, v in pools.items() if v[1] == 0), None)
                if stale is None:
                    raise HTTPException(429, "Too many active workload pools")
                del pools[stale]
            pools[key] = [asyncio.Semaphore(profile.slots), 0]
        pool = pools[key]
        pool[1] += 1
        prefill_target, chunk_target = timing(options.seed, options.index, profile)
        request_id = f"{options.run_id}-{options.index:03d}"

        def event(delta=None, *, finish=None, usage=None, measurements=None):
            payload = {"id": "chatcmpl-" + request_id, "object": "chat.completion.chunk",
                       "created": int(time.time()), "model": body.model,
                       "choices": [] if usage else [{"index": 0, "delta": delta or {},
                                                      "finish_reason": finish}]}
            if usage:
                payload["usage"] = usage
            if measurements:
                payload["observatory"] = measurements
            return "data: " + json.dumps(payload) + "\n\n"

        async def generate():
            attrs = {"observatory.run_id": options.run_id,
                     "observatory.request_id": request_id,
                     "observatory.scenario": options.scenario.value}
            acquired = False
            started = perf_counter()
            try:
                with span("inference.serve", **attrs) as serving_span:
                    with span("queue.wait", **attrs):
                        await pool[0].acquire()
                        acquired = True
                    queue_ms = (perf_counter() - started) * 1000
                    t = perf_counter()
                    with span("model.prefill", **attrs):
                        await asyncio.sleep(prefill_target / 1000)
                    prefill_ms = (perf_counter() - t) * 1000
                    t = perf_counter()
                    with span("model.decode", **attrs):
                        for index in range(profile.chunks):
                            await asyncio.sleep(chunk_target / 1000)
                            yield event({"role": "assistant", "content": "evidence "})
                            if profile.fail_every and (options.index + 1) % profile.fail_every == 0 and index == 5:
                                serving_span.set_level("error")
                                serving_span.set_attribute("error.type", "StreamInterrupted")
                                logfire.error("Inference stream interrupted", **attrs)
                                yield "data: " + json.dumps({"error": {"message": "Controlled stream interruption",
                                    "type": "StreamInterrupted", "code": "stream_interrupted"}}) + "\n\n"
                                return
                    decode_ms = (perf_counter() - t) * 1000
                    measurements = {"source": "synthetic", "queue_ms": queue_ms,
                                    "prefill_ms": prefill_ms, "decode_ms": decode_ms,
                                    "server_trace_id": trace_id(), "token_basis": "fixture-units"}
                    for name, value in measurements.items():
                        serving_span.set_attribute("observatory." + name, value)
                    yield event(finish="stop")
                    yield event(usage={"prompt_tokens": 128, "completion_tokens": profile.chunks,
                                       "total_tokens": 128 + profile.chunks}, measurements=measurements)
                    yield "data: [DONE]\n\n"
            except asyncio.CancelledError:
                logfire.info("Serving request cancelled", **attrs)
                raise
            finally:
                if acquired:
                    pool[0].release()
                pool[1] -= 1

        return StreamingResponse(generate(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app
