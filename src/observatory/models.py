from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Scenario(StrEnum):
    baseline = "baseline"
    queue_pressure = "queue-pressure"
    slow_prefill = "slow-prefill"
    interrupted_stream = "interrupted-stream"
    recovery = "recovery"


class RunSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Scenario = Scenario.baseline
    requests: int = Field(24, ge=1, le=120)
    concurrency: int = Field(8, ge=1, le=32)
    seed: int = Field(42, ge=0, le=2**31 - 1)


class RequestResult(BaseModel):
    request_id: str
    index: int
    status: str
    trace_id: str
    duration_ms: float
    queue_ms: float
    prefill_ms: float
    first_chunk_ms: float | None
    decode_ms: float
    input_tokens: int
    output_tokens: int
    error: str | None = None


class Run(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    spec: RunSpec
    status: str = "pending"
    trace_id: str = ""
    source: str = "synthetic"
    results: list[RequestResult] = Field(default_factory=list)
    failure: str | None = None
