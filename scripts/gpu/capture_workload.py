"""Run bounded real-engine workloads and preserve inputs, output chunks and timings."""

import argparse
import asyncio
import json
import platform
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

import httpx
import logfire
from openai import AsyncOpenAI
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

MODEL = "google/gemma-4-12B-it"
REVISION = "707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7"


def now():
    return datetime.now(UTC).isoformat()


def prompt_for(scenario, index):
    prefix = f"Request {scenario} item {index}. "
    if scenario == "long-context":
        document = "\n".join(
            f"Record {i}: service alpha accepted a request, queued it, processed tokens, "
            "and returned the response. The operator recorded latency and throughput."
            for i in range(210)
        )
        return prefix + "Summarize the operational risks in this log extract:\n" + document
    return prefix + (
        "Explain how to distinguish queueing delay, prefill latency and decode latency "
        "in an LLM inference service. Give a practical debugging checklist."
    )


async def main(args):
    if args.output.exists() and any(args.output.iterdir()):
        raise SystemExit("Output directory must be empty; preserve previous captures separately")
    args.output.mkdir(parents=True, exist_ok=True)
    logfire.configure(
        send_to_logfire=False,
        console=False,
        metrics=False,
        service_name="inference-h100-client",
        environment="gpu-lab",
        distributed_tracing=True,
        inspect_arguments=False,
        resource_attributes={
            "observatory.source": "real-inference",
            "observatory.engine": "vllm",
            "observatory.capture_id": args.capture_id,
        },
        additional_span_processors=[
            BatchSpanProcessor(OTLPSpanExporter(endpoint=args.otlp), schedule_delay_millis=500)
        ],
    )
    plans = (
        [("smoke", 2, 1, 48)]
        if args.smoke
        else [
            ("baseline", 8, 1, 128),
            ("queue-pressure", 32, 16, 256),
            ("long-context", 8, 2, 128),
            ("recovery", 8, 1, 128),
            ("invalid-request", 1, 1, 9000),
            ("client-early-close", 4, 2, 256),
        ]
    )
    manifest = {
        "capture_id": args.capture_id,
        "started_at": now(),
        "model": MODEL,
        "model_revision": REVISION,
        "platform": platform.platform(),
        "client_versions": {p: version(p) for p in ["logfire", "openai", "httpx"]},
        "plans": plans,
        "base_url": args.base_url,
        "notes": [
            "Real model inference on one remote H100, reached over an SSH tunnel.",
            "Client timings include network and SSH transport; native engine timings are separate.",
            "ignore_eos=True deliberately fixes output length for load scenarios.",
            "Client early close is intentional; missing final usage remains null.",
        ],
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    results = []
    async with (
        httpx.AsyncClient(timeout=15) as metrics_http,
        AsyncOpenAI(
            base_url=args.base_url + "/v1",
            api_key="unused-local-tunnel",
            max_retries=0,
            timeout=120,
        ) as client,
    ):
        models = await metrics_http.get(args.base_url + "/v1/models")
        models.raise_for_status()
        (args.output / "models.json").write_text(models.text)
        for scenario, count, concurrency, max_tokens in plans:
            before = await metrics_http.get(args.base_url + "/metrics")
            before.raise_for_status()
            (args.output / f"{scenario}-metrics-before.prom").write_text(before.text)
            semaphore = asyncio.Semaphore(concurrency)
            events = args.output / f"{scenario}-requests.jsonl"
            with logfire.span(
                "gpu.workload {scenario}",
                scenario=scenario,
                **{"observatory.capture_id": args.capture_id, "observatory.scenario": scenario},
            ):

                async def request(index):
                    async with semaphore:
                        request_id = f"{args.capture_id}-{scenario}-{index:03d}"
                        prompt = prompt_for(scenario, index)
                        row = {
                            "request_id": request_id,
                            "scenario": scenario,
                            "started_at": now(),
                            "prompt": prompt,
                            "seed": 42,
                            "max_tokens": max_tokens,
                            "status": "ok",
                            "usage": None,
                            "engine_metrics": None,
                            "chunks": [],
                        }
                        start = perf_counter()
                        try:
                            with logfire.span(
                                "chat {model}",
                                model=MODEL,
                                **{
                                    "observatory.capture_id": args.capture_id,
                                    "observatory.request_id": request_id,
                                    "observatory.scenario": scenario,
                                    "gen_ai.system": "openai",
                                    "gen_ai.provider.name": "openai",
                                    "gen_ai.operation.name": "chat",
                                    "gen_ai.request.model": MODEL,
                                    "gen_ai.response.model": MODEL,
                                    "gen_ai.request.max_tokens": row["max_tokens"],
                                    "gen_ai.request.temperature": 0.0,
                                },
                            ) as span:
                                context = trace.get_current_span().get_span_context()
                                row["trace_id"] = f"{context.trace_id:032x}"
                                row["span_id"] = f"{context.span_id:016x}"
                                headers = {"X-Request-Id": request_id}
                                propagate.inject(headers)
                                row["traceparent"] = headers["traceparent"]
                                stream = await client.chat.completions.create(
                                    model=MODEL,
                                    messages=[{"role": "user", "content": prompt}],
                                    stream=True,
                                    stream_options={"include_usage": True},
                                    temperature=0,
                                    seed=42,
                                    max_tokens=row["max_tokens"],
                                    extra_headers=headers,
                                    extra_body={
                                        "ignore_eos": True,
                                        "chat_template_kwargs": {"enable_thinking": False},
                                    },
                                )
                                content_chunks = 0
                                async with stream:
                                    async for chunk in stream:
                                        elapsed = perf_counter() - start
                                        row["chunks"].append(
                                            {
                                                "elapsed_s": elapsed,
                                                "chunk": chunk.model_dump(mode="json"),
                                            }
                                        )
                                        if "first_chunk_s" not in row:
                                            row["first_chunk_s"] = elapsed
                                            span.set_attribute(
                                                "gen_ai.client.operation.time_to_first_chunk",
                                                elapsed,
                                            )
                                        if chunk.choices and chunk.choices[0].delta.content:
                                            content_chunks += 1
                                            if "first_content_s" not in row:
                                                row["first_content_s"] = elapsed
                                                span.set_attribute(
                                                    "observatory.first_content_ms", elapsed * 1000
                                                )
                                        if chunk.usage:
                                            row["usage"] = chunk.usage.model_dump(mode="json")
                                            span.set_attribute(
                                                "gen_ai.usage.input_tokens",
                                                chunk.usage.prompt_tokens,
                                            )
                                            span.set_attribute(
                                                "gen_ai.usage.output_tokens",
                                                chunk.usage.completion_tokens,
                                            )
                                        if (chunk.model_extra or {}).get("metrics"):
                                            row["engine_metrics"] = chunk.model_extra["metrics"]
                                        if chunk.choices and chunk.choices[0].finish_reason:
                                            span.set_attribute(
                                                "gen_ai.response.finish_reasons",
                                                [chunk.choices[0].finish_reason],
                                            )
                                        if scenario == "client-early-close" and content_chunks >= 5:
                                            row["status"] = "intentional_early_close"
                                            span.set_attribute(
                                                "observatory.intentional_early_close", True
                                            )
                                            break
                                if row["status"] == "ok" and row["usage"] is None:
                                    raise RuntimeError("Completed stream missing final token usage")
                                span.set_attribute("observatory.content_chunks", content_chunks)
                        except Exception as exc:
                            row["status"] = "error"
                            row["error_type"] = type(exc).__name__
                            row["error_message"] = str(exc)
                        row["duration_s"] = perf_counter() - start
                        row["ended_at"] = now()
                        with events.open("a") as output:
                            output.write(json.dumps(row) + "\n")
                            output.flush()
                        results.append(row)

                await asyncio.gather(*(request(i) for i in range(count)))
            after = await metrics_http.get(args.base_url + "/metrics")
            after.raise_for_status()
            (args.output / f"{scenario}-metrics-after.prom").write_text(after.text)
            logfire.force_flush(timeout_millis=30000)
            rows = [r for r in results if r["scenario"] == scenario]
            print(
                json.dumps(
                    {
                        "scenario": scenario,
                        "requests": len(rows),
                        "errors": sum(r["status"] == "error" for r in rows),
                        "early_close": sum(r["status"] == "intentional_early_close" for r in rows),
                    }
                ),
                flush=True,
            )
    manifest["ended_at"] = now()
    manifest["requests"] = len(results)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (args.output / "request-index.json").write_text(
        json.dumps(
            [{k: v for k, v in r.items() if k not in ["prompt", "chunks"]} for r in results],
            indent=2,
        )
    )
    logfire.force_flush(timeout_millis=30000)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--otlp", default="http://127.0.0.1:14318/v1/traces")
    parser.add_argument("--capture-id", default="h100-gemma4-20260927")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    asyncio.run(main(parser.parse_args()))
