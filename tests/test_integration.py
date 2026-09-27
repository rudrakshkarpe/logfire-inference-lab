import json
import subprocess
import sys

import httpx
import pytest

from observatory.store import Store


@pytest.fixture(scope="module")
def executed(serving_process):
    path, env, port = serving_process
    runs = {}
    for scenario in [
        "baseline",
        "queue-pressure",
        "slow-prefill",
        "interrupted-stream",
        "recovery",
    ]:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "observatory.cli",
                "run",
                "--scenario",
                scenario,
                "--requests",
                "8",
            ],
            cwd=path,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        runs[scenario] = json.loads(result.stdout)["run"]
    return path, runs


def test_queue_pressure_and_prefill_have_different_signatures(executed):
    _, runs = executed
    baseline = runs["baseline"]["summary"]
    queue = runs["queue-pressure"]["summary"]
    prefill = runs["slow-prefill"]["summary"]
    recovery = runs["recovery"]["summary"]
    assert queue["p95_queue_ms"] > baseline["p95_queue_ms"] + 500
    assert prefill["p95_prefill_ms"] > baseline["p95_prefill_ms"] + 400
    assert recovery["p95_queue_ms"] < queue["p95_queue_ms"] / 2


def test_failed_streams_do_not_invent_final_usage(executed):
    path, runs = executed
    run = Store(path / "data/observatory.db").get(runs["interrupted-stream"]["id"])
    failed = [r for r in run.results if r.status == "error"]
    assert len(failed) == 2
    assert all(r.first_chunk_ms is not None and r.observed_chunks == 6 for r in failed)
    assert all(r.output_tokens is None and r.queue_ms is None for r in failed)
    assert runs["recovery"]["summary"]["errors"] == 0


def test_trace_has_client_to_server_parent_edges(executed):
    path, runs = executed
    trace = runs["baseline"]["trace_id"]
    spans = []
    for f in (path / "data").glob("*-spans.jsonl"):
        spans.extend(json.loads(line) for line in f.read_text().splitlines())
    spans = [
        s
        for s in spans
        if s["trace_id"] == trace and s["attributes"].get("logfire.span_type") != "pending_span"
    ]
    client_ids = {s["span_id"] for s in spans if s["service"] == "inference-application"}
    server = [s for s in spans if s["service"] == "inference-serving"]
    assert len([s for s in server if s["parent_id"] in client_ids]) == 8
    assert len([s for s in server if s["name"] == "queue.wait"]) == 8
    assert len([s for s in server if s["name"] == "model.prefill"]) == 8
    assert len([s for s in server if s["name"] == "model.decode"]) == 8
    assert all(s["end_ns"] >= s["start_ns"] for s in spans)


def test_serving_rejects_unsupported_and_unbounded_requests(serving_process):
    _, _, port = serving_process
    url = f"http://127.0.0.1:{port}/v1/chat/completions"
    body = {"messages": [{"role": "user", "content": "fixture"}], "stream": False}
    assert httpx.post(url, json=body).status_code == 400
    body.update(stream=True, observatory={"index": -1})
    assert httpx.post(url, json=body).status_code == 422
    body.update(observatory={}, model="unavailable")
    assert httpx.post(url, json=body).status_code == 404
