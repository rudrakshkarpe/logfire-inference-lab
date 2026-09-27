"""Local, ignored trace evidence for checking cross-process parent relationships."""

import json
import threading
from pathlib import Path

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult


class JsonlExporter(SpanExporter):
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        path.touch(mode=0o600, exist_ok=True)
        self.lock = threading.Lock()

    def export(self, spans):
        with self.lock, self.path.open("a") as output:
            for span in spans:
                # Store structure and workload attributes only, never prompt bodies or headers.
                attrs = {
                    k: v
                    for k, v in span.attributes.items()
                    if k.startswith(
                        (
                            "observatory.",
                            "gen_ai.usage.",
                            "gen_ai.request.model",
                            "gen_ai.client.operation.",
                            "error.type",
                            "logfire.span_type",
                        )
                    )
                }
                output.write(
                    json.dumps(
                        {
                            "name": span.name,
                            "trace_id": f"{span.context.trace_id:032x}",
                            "span_id": f"{span.context.span_id:016x}",
                            "parent_id": f"{span.parent.span_id:016x}" if span.parent else None,
                            "service": span.resource.attributes.get("service.name"),
                            "start_ns": span.start_time,
                            "end_ns": span.end_time,
                            "status": span.status.status_code.name,
                            "attributes": attrs,
                        }
                    )
                    + "\n"
                )
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass
