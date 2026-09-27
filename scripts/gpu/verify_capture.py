"""Verify an archived capture and summarize native engine/client relationships."""

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest


def values(attributes):
    result = {}
    for attribute in attributes:
        value = attribute.value
        field = value.WhichOneof("value")
        if field in ("string_value", "bool_value", "int_value", "double_value"):
            result[attribute.key] = getattr(value, field)
    return result


def load_spans(directory):
    spans = {}
    for path in sorted(directory.glob("*.pb")):
        message = ExportTraceServiceRequest.FromString(path.read_bytes())
        for resource in message.resource_spans:
            resource_attrs = values(resource.resource.attributes)
            for scope in resource.scope_spans:
                for span in scope.spans:
                    attrs = values(span.attributes)
                    if attrs.get("logfire.span_type") == "pending_span":
                        continue
                    key = (span.trace_id.hex(), span.span_id.hex())
                    row = {
                        "trace_id": key[0],
                        "span_id": key[1],
                        "parent_id": span.parent_span_id.hex(),
                        "name": span.name,
                        "service": resource_attrs.get("service.name"),
                        "start_ns": span.start_time_unix_nano,
                        "end_ns": span.end_time_unix_nano,
                        "duration_s": (span.end_time_unix_nano - span.start_time_unix_nano) / 1e9,
                        "status": span.status.code,
                        "exception_events": sum(e.name == "exception" for e in span.events),
                        "attributes": attrs,
                        "resource": resource_attrs,
                    }
                    if key in spans:
                        assert spans[key] == row, f"Conflicting duplicate span {key}"
                    spans[key] = row
    return list(spans.values())


def percentile(rows, key, p=0.95):
    data = sorted(r[key] for r in rows if r.get(key) is not None)
    return data[max(0, math.ceil(p * len(data)) - 1)] if data else None


def summarize_scenario(rows, native):
    usage = [r["usage"] for r in rows if r.get("usage") is not None]
    summary = {
        "requests": len(rows),
        "statuses": dict(collections.Counter(r["status"] for r in rows)),
        "p95_first_content_s": percentile(rows, "first_content_s"),
        "p95_duration_s": percentile(rows, "duration_s"),
        "requests_with_usage": len(usage),
        "requests_without_usage": len(rows) - len(usage),
        "input_tokens": sum(u["prompt_tokens"] for u in usage) if usage else None,
        "output_tokens": sum(u["completion_tokens"] for u in usage) if usage else None,
        "engine_request_spans": len(native),
    }
    for key in ("time_in_queue", "time_in_model_prefill", "time_in_model_decode"):
        summary[f"p95_engine_{key}_s"] = percentile(
            [s["attributes"] for s in native], f"gen_ai.latency.{key}"
        )
    return summary


def validate_outcomes(index, manifest):
    """A complete file is not proof that the planned workload succeeded."""
    expected = {name: count for name, count, _, _ in manifest["plans"]}
    actual = dict(collections.Counter(r["scenario"] for r in index))
    if not index or actual != expected:
        raise ValueError(f"Incomplete workload: expected {expected}, found {actual}")
    if len({r["request_id"] for r in index}) != len(index):
        raise ValueError("Duplicate request IDs in workload")
    for request in index:
        status = {
            "invalid-request": "error",
            "client-early-close": "intentional_early_close",
        }.get(request["scenario"], "ok")
        if request["status"] != status:
            raise ValueError(f"Unexpected outcome for {request['request_id']}: {request['status']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--workload", default="workload")
    args = parser.parse_args()
    index = json.loads((args.directory / args.workload / "request-index.json").read_text())
    manifest = json.loads((args.directory / args.workload / "manifest.json").read_text())
    validate_outcomes(index, manifest)
    receipts = [
        json.loads(line)
        for line in (args.directory / "otlp/receipts.jsonl").read_text().splitlines()
    ]
    for row in receipts:
        path = args.directory / "otlp" / row["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
    spans = load_spans(args.directory / "otlp")
    summary = {
        "requests": len(index),
        "unique_final_spans": len(spans),
        "services": dict(collections.Counter(s["service"] for s in spans)),
        "forward_statuses": dict(collections.Counter(str(r["forward_status"]) for r in receipts)),
        "scenarios": {},
        "request_links": [],
    }
    for request in index:
        clients = [
            s
            for s in spans
            if s["trace_id"] == request["trace_id"] and s["span_id"] == request["span_id"]
        ]
        assert len(clients) == 1, request["request_id"]
        native = [
            s
            for s in spans
            if s["service"] == "vllm-h100-serving"
            and s["name"] == "llm_request"
            and s["trace_id"] == request["trace_id"]
            and s["parent_id"] == request["span_id"]
        ]
        summary["request_links"].append(
            {
                "request_id": request["request_id"],
                "status": request["status"],
                "trace_id": request["trace_id"],
                "client_span_id": request["span_id"],
                "engine_children": native,
            }
        )
        if request["status"] == "ok":
            assert request["usage"], request["request_id"]
            assert len(native) == 1, f"Expected one linked engine span for {request['request_id']}"
            attrs = native[0]["attributes"]
            assert attrs["gen_ai.usage.prompt_tokens"] == request["usage"]["prompt_tokens"]
            assert attrs["gen_ai.usage.completion_tokens"] == request["usage"]["completion_tokens"]
        if request["scenario"] == "invalid-request":
            assert request["error_type"] == "BadRequestError"
            assert clients[0]["exception_events"] > 0
    for scenario in dict.fromkeys(r["scenario"] for r in index):
        rows = [r for r in index if r["scenario"] == scenario]
        ids = {r["request_id"] for r in rows}
        native = [
            child
            for link in summary["request_links"]
            if link["request_id"] in ids
            for child in link["engine_children"]
        ]
        summary["scenarios"][scenario] = summarize_scenario(rows, native)
    output = args.directory / f"{args.workload}-verification.json"
    output.write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "request_links"}, indent=2))


if __name__ == "__main__":
    main()
