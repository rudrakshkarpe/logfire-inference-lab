import math
from collections.abc import Iterable

from observatory.models import Run


def percentile(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    return round(ordered[max(0, math.ceil(quantile * len(ordered)) - 1)], 2)


def summary(run: Run) -> dict:
    results = run.results
    errors = sum(item.status != "ok" for item in results)
    first = [item.first_chunk_ms for item in results if item.first_chunk_ms is not None]
    return {
        "completed": len(results),
        "requested": run.spec.requests,
        "errors": errors,
        "error_rate": round(errors / len(results), 4) if results else 0,
        "p50_first_chunk_ms": percentile(first, 0.5),
        "p95_first_chunk_ms": percentile(first, 0.95),
        "p95_duration_ms": percentile((item.duration_ms for item in results), 0.95),
        "p95_queue_ms": percentile(
            (item.queue_ms for item in results if item.queue_ms is not None), 0.95
        ),
        "p95_prefill_ms": percentile(
            (item.prefill_ms for item in results if item.prefill_ms is not None), 0.95
        ),
        "output_tokens": sum(item.output_tokens or 0 for item in results),
        "first_chunk_samples": len(first),
    }


def serialize(run: Run, detail: bool = False) -> dict:
    data = run.model_dump(mode="json", exclude=set() if detail else {"results"})
    data["summary"] = summary(run)
    return data
