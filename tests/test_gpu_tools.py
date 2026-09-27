"""Offline regression checks for portable GPU evidence; no Pod or credentials needed."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)


def load_tool(name):
    path = Path(__file__).resolve().parents[1] / "scripts/gpu" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


replay = load_tool("replay_otlp")
verify = load_tool("verify_capture")
archive = load_tool("otlp_archive")


@pytest.fixture
def recorded_batch(tmp_path):
    message = ExportTraceServiceRequest()
    span = message.resource_spans.add().scope_spans.add().spans.add()
    span.name = "llm_request"
    span.trace_id = bytes.fromhex("01" * 16)
    span.span_id = bytes.fromhex("02" * 8)
    span.start_time_unix_nano = 100
    span.end_time_unix_nano = 200
    payload = message.SerializeToString()
    (tmp_path / "one.pb").write_bytes(payload)
    receipt = {"file": "one.pb", "sha256": hashlib.sha256(payload).hexdigest()}
    (tmp_path / "receipts.jsonl").write_text(json.dumps(receipt) + "\n")
    return tmp_path, message


def test_replay_loads_verified_payload_without_modification(recorded_batch):
    directory, original = recorded_batch
    batches = replay.load_verified_batches(directory)
    assert batches[0][1] == original
    assert (directory / "one.pb").read_bytes() == original.SerializeToString()


@pytest.mark.parametrize("damage", ["changed", "missing", "extra", "no_journal"])
def test_replay_rejects_incomplete_or_modified_archives(recorded_batch, damage):
    directory, _ = recorded_batch
    if damage == "changed":
        (directory / "one.pb").write_bytes(b"altered payload")
    elif damage == "missing":
        (directory / "one.pb").unlink()
    elif damage == "extra":
        (directory / "extra.pb").write_bytes(b"unrecorded payload")
    else:
        (directory / "receipts.jsonl").unlink()
    with pytest.raises(ValueError):
        replay.load_verified_batches(directory)


def test_missing_usage_is_unknown_not_zero():
    rows = [{"status": "intentional_early_close", "usage": None, "duration_s": 0.3}]
    summary = verify.summarize_scenario(rows, [])
    assert summary["input_tokens"] is None
    assert summary["output_tokens"] is None
    assert summary["requests_with_usage"] == 0
    assert summary["requests_without_usage"] == 1
    assert summary["p95_engine_time_in_queue_s"] is None


def test_partial_usage_reports_coverage_and_preserves_real_zero():
    rows = [
        {"status": "ok", "usage": {"prompt_tokens": 12, "completion_tokens": 0}},
        {"status": "error", "usage": None},
    ]
    summary = verify.summarize_scenario(rows, [])
    assert summary["input_tokens"] == 12
    assert summary["output_tokens"] == 0
    assert summary["requests_with_usage"] == summary["requests_without_usage"] == 1


def test_http_200_can_contain_an_otlp_partial_rejection():
    message = ExportTraceServiceResponse()
    message.partial_success.rejected_spans = 2
    response = io.BytesIO(message.SerializeToString())
    response.status = 200
    result = archive.forwarding_result(response)
    assert result["forward_status"] == 200
    assert result["forward_rejected_spans"] == 2


def test_malformed_forward_response_is_recorded_as_unverified():
    response = io.BytesIO(b"not protobuf")
    response.status = 200
    result = archive.forwarding_result(response)
    assert result["forward_error"] == "InvalidOTLPResponse"
    assert "forward_rejected_spans" not in result


@pytest.mark.parametrize("problem", ["unexpected_error", "missing_request", "duplicate_id"])
def test_verification_rejects_unsuccessful_or_incomplete_workloads(problem):
    manifest = {"plans": [["baseline", 2, 1, 128]]}
    rows = [
        {"scenario": "baseline", "status": "ok", "request_id": "a"},
        {"scenario": "baseline", "status": "ok", "request_id": "b"},
    ]
    if problem == "unexpected_error":
        rows[1]["status"] = "error"
    elif problem == "missing_request":
        rows.pop()
    else:
        rows[1]["request_id"] = "a"
    with pytest.raises(ValueError):
        verify.validate_outcomes(rows, manifest)
