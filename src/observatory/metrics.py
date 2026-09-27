import logfire


class Metrics:
    def __init__(self):
        self.duration = logfire.metric_histogram("observatory.request.duration", unit="s")
        self.first_chunk = logfire.metric_histogram("observatory.client.first_content", unit="s")
        self.queue = logfire.metric_histogram("observatory.queue.duration", unit="s")
        self.requests = logfire.metric_counter("observatory.requests", unit="{request}")

    def record(self, run, result):
        attrs = {
            "observatory.scenario": run.spec.scenario.value,
            "observatory.source": "synthetic",
            "gen_ai.request.model": "observatory-stream",
            "observatory.status": result.status,
        }
        self.duration.record(result.duration_ms / 1000, attrs)
        if result.queue_ms is not None:
            self.queue.record(result.queue_ms / 1000, attrs)
        self.requests.add(1, attrs)
        if result.first_chunk_ms is not None:
            self.first_chunk.record(result.first_chunk_ms / 1000, attrs)
