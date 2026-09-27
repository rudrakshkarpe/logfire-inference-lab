"""Inspect or replay an immutable OTLP archive to an explicitly selected backend."""

import argparse
import hashlib
import json
import os
import time
import urllib.request
import uuid
from pathlib import Path

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)


def load_verified_batches(directory):
    """Check every archived payload before any replay network request is made."""
    receipts = directory / "receipts.jsonl"
    if not receipts.is_file():
        raise ValueError("Archive is missing receipts.jsonl; cannot verify payload integrity")
    expected = {}
    for line in receipts.read_text().splitlines():
        row = json.loads(line)
        name = row["file"]
        if name != Path(name).name or name in expected:
            raise ValueError(f"Invalid or duplicate archive receipt: {name}")
        expected[name] = row["sha256"]
    paths = sorted(directory.glob("*.pb"))
    if {p.name for p in paths} != set(expected):
        raise ValueError("Archive payloads do not match the receipt journal")
    batches = []
    for path in paths:
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != expected[path.name]:
            raise ValueError(f"Archive checksum mismatch: {path.name}")
        batches.append((path, ExportTraceServiceRequest.FromString(body)))
    return batches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--endpoint", help="Full OTLP/HTTP traces URL; required with --send")
    parser.add_argument(
        "--send", action="store_true", help="Actually transmit; default only inspects"
    )
    parser.add_argument("--shift-to-now", action="store_true")
    parser.add_argument("--new-trace-ids", action="store_true")
    args = parser.parse_args()
    if args.send and not args.endpoint:
        parser.error("--send requires --endpoint")
    # Tokens and optional dataset headers stay in the environment, never arguments or archives.
    headers = json.loads(os.environ.get("OTLP_REPLAY_HEADERS_JSON", "{}"))
    headers["Content-Type"] = "application/x-protobuf"
    batches = load_verified_batches(args.directory)
    spans = [
        s
        for _, m in batches
        for r in m.resource_spans
        for scope in r.scope_spans
        for s in scope.spans
    ]
    if not spans:
        raise SystemExit("Archive has no spans")
    latest = max(s.end_time_unix_nano for s in spans)
    shift = time.time_ns() - latest if args.shift_to_now else 0
    mapping = {s.trace_id: uuid.uuid4().bytes for s in spans} if args.new_trace_ids else {}
    for s in spans:
        for link in s.links:
            if args.new_trace_ids and link.trace_id not in mapping:
                mapping[link.trace_id] = uuid.uuid4().bytes
    print(
        json.dumps(
            {
                "batches": len(batches),
                "spans": len(spans),
                "traces": len({s.trace_id for s in spans}),
                "send": args.send,
                "timestamp_shift_ns": shift,
                "new_trace_ids": args.new_trace_ids,
            }
        )
    )
    if not args.send:
        return
    for path, message in batches:
        for resource in message.resource_spans:
            attribute = resource.resource.attributes.add()
            attribute.key = "observatory.replayed"
            attribute.value.bool_value = True
            original = resource.resource.attributes.add()
            original.key = "observatory.archive_batch_sha256"
            original.value.string_value = hashlib.sha256(path.read_bytes()).hexdigest()
            for scope in resource.scope_spans:
                for span in scope.spans:
                    span.start_time_unix_nano += shift
                    span.end_time_unix_nano += shift
                    for event in span.events:
                        event.time_unix_nano += shift
                    if mapping:
                        span.trace_id = mapping[span.trace_id]
                        for link in span.links:
                            link.trace_id = mapping[link.trace_id]
        request = urllib.request.Request(
            args.endpoint, data=message.SerializeToString(), headers=headers
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            reply = ExportTraceServiceResponse.FromString(response.read())
            if reply.partial_success.rejected_spans:
                raise SystemExit(
                    f"Backend rejected {reply.partial_success.rejected_spans} spans in {path.name}"
                )
            print(json.dumps({"file": path.name, "status": response.status}))


if __name__ == "__main__":
    main()
