from pathlib import Path

import logfire
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from observatory.capture import JsonlExporter
from observatory.settings import Settings

SOURCE = {"observatory.source": "synthetic", "observatory.engine": "workload-model"}


def configure(settings: Settings, service_name: str = "inference-observatory"):
    token = settings.logfire_token.get_secret_value() if settings.logfire_token else None
    processors = (
        [SimpleSpanProcessor(JsonlExporter(Path("data") / f"{service_name}-spans.jsonl"))]
        if settings.observatory_capture_traces
        else []
    )
    logfire.configure(
        send_to_logfire=settings.observatory_export,
        token=token or None,
        service_name=service_name,
        service_version="0.1.0",
        environment="lab",
        resource_attributes=SOURCE,
        console=False,
        additional_span_processors=processors,
        inspect_arguments=False,
        distributed_tracing=True,
        advanced=logfire.AdvancedOptions(base_url=settings.logfire_base_url),
    )


def trace_id() -> str:
    return format(trace.get_current_span().get_span_context().trace_id, "032x")


def span(name: str, **attributes):
    return logfire.span(name, **SOURCE, **attributes)


def flush() -> bool:
    return logfire.force_flush(timeout_millis=10000)
