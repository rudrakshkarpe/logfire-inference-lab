import random
from dataclasses import asdict, dataclass

from observatory.models import Scenario


@dataclass(frozen=True)
class Profile:
    title: str
    description: str
    slots: int
    prefill_ms: float
    chunk_ms: float
    chunks: int
    fail_every: int
    hypothesis: str
    investigate: str


PROFILES = {
    Scenario.baseline: Profile(
        "Baseline",
        "A healthy reference workload",
        8,
        55,
        12,
        12,
        0,
        "Short queue waits and stable first-chunk latency.",
        "Compare against an incident run.",
    ),
    Scenario.queue_pressure: Profile(
        "Queue pressure",
        "Requests compete for two execution slots",
        2,
        70,
        24,
        18,
        0,
        "Queue wait dominates first-chunk latency.",
        "Expand inference.request and compare queue.wait with model.prefill.",
    ),
    Scenario.slow_prefill: Profile(
        "Slow prefill",
        "Long context preparation before the first chunk",
        8,
        650,
        12,
        12,
        0,
        "Prefill is slow even without significant queueing.",
        "Compare model.prefill duration with the baseline run.",
    ),
    Scenario.interrupted_stream: Profile(
        "Interrupted stream",
        "Every fourth request fails mid-stream",
        8,
        60,
        20,
        16,
        4,
        "A response can start successfully and still fail during decoding.",
        "Inspect error spans and partial output counts; first-chunk latency alone misses this.",
    ),
    Scenario.recovery: Profile(
        "Recovery",
        "Execution capacity restored after queue pressure",
        8,
        70,
        24,
        18,
        0,
        "Restoring slots reduces queueing under the same offered concurrency.",
        "Compare queue wait and first-chunk p95 with queue pressure using the same seed.",
    ),
}


def catalogue():
    return [{"id": key.value, **asdict(value)} for key, value in PROFILES.items()]


def timing(seed: int, index: int, profile: Profile) -> tuple[float, float]:
    rng = random.Random((seed << 16) + index)
    return profile.prefill_ms * rng.uniform(0.85, 1.15), profile.chunk_ms * rng.uniform(0.9, 1.1)
