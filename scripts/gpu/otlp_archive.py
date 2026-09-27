"""Archive OTLP protobuf before optionally forwarding it to a configured backend.

This loopback-only lab receiver preserves original payloads for later replay.
It acknowledges durable local capture, not successful remote ingestion.
"""

import argparse
import gzip
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from google.protobuf.json_format import MessageToJson
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)


def forwarding_result(response):
    """Keep an OTLP partial rejection distinct from an HTTP success."""
    result = {"forward_status": response.status}
    try:
        reply = ExportTraceServiceResponse.FromString(response.read())
        result["forward_rejected_spans"] = reply.partial_success.rejected_spans
    except Exception:
        result["forward_error"] = "InvalidOTLPResponse"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--port", type=int, default=14318)
    parser.add_argument("--logfire-credentials", type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    credentials = (
        json.loads(args.logfire_credentials.read_text()) if args.logfire_credentials else None
    )
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            if self.path != "/v1/traces":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 32 * 1024 * 1024:
                self.send_error(413)
                return
            body = self.rfile.read(length)
            try:
                if self.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                message = ExportTraceServiceRequest.FromString(body)
            except Exception:
                self.send_error(400)
                return
            stem = f"{time.time_ns()}-{uuid.uuid4().hex[:8]}"
            protobuf = args.directory / f"{stem}.pb"
            with protobuf.open("xb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            (args.directory / f"{stem}.json").write_text(MessageToJson(message))
            count = sum(len(s.spans) for r in message.resource_spans for s in r.scope_spans)
            result = {
                "file": protobuf.name,
                "sha256": hashlib.sha256(body).hexdigest(),
                "spans": count,
                "forward_status": None,
            }
            if credentials:
                request = urllib.request.Request(
                    credentials["logfire_api_url"].rstrip("/") + "/v1/traces",
                    data=body,
                    headers={
                        "Content-Type": "application/x-protobuf",
                        "Authorization": credentials["token"],
                    },
                )
                try:
                    with urllib.request.urlopen(request, timeout=20) as response:
                        result.update(forwarding_result(response))
                except urllib.error.HTTPError as exc:
                    result["forward_status"] = exc.code
                except Exception as exc:
                    result["forward_error"] = type(exc).__name__
            with lock, (args.directory / "receipts.jsonl").open("a") as journal:
                journal.write(json.dumps(result) + "\n")
                journal.flush()
                os.fsync(journal.fileno())
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()

    print(f"Archiving OTLP on 127.0.0.1:{args.port} into {args.directory}", flush=True)
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
