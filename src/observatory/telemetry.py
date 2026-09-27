import logfire
from opentelemetry import trace

from observatory.settings import Settings

SOURCE = {"observatory.source": "synthetic", "observatory.engine": "workload-model"}


def configure(settings: Settings):
    token = settings.logfire_token.get_secret_value() if settings.logfire_token else None
    logfire.configure(
        send_to_logfire=settings.observatory_export,
        token=token or None,
        service_name="inference-observatory",
        service_version="0.1.0",
        environment="lab",
        resource_attributes=SOURCE,
        console=False,
        inspect_arguments=False,
        advanced=logfire.AdvancedOptions(base_url=settings.logfire_base_url),
    )


def trace_id() -> str:
    return format(trace.get_current_span().get_span_context().trace_id, "032x")


def span(name: str, **attributes):
    return logfire.span(name, **SOURCE, **attributes)


def flush() -> bool:
    return logfire.force_flush(timeout_millis=10000)
