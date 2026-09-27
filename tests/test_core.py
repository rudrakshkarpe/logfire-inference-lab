import pytest
from pydantic import ValidationError

from observatory.analysis import percentile, summary
from observatory.models import Run, RunSpec, Scenario
from observatory.scenarios import PROFILES, timing
from observatory.store import Store


@pytest.mark.parametrize(
    "field,value",
    [
        ("requests", 0),
        ("requests", 121),
        ("concurrency", 33),
        ("seed", -1),
        ("scenario", "unknown"),
    ],
)
def test_unsafe_workloads_are_rejected(field, value):
    with pytest.raises(ValidationError):
        RunSpec(**{field: value})


def test_empty_metrics_are_unknown_not_zero():
    stats = summary(Run(spec=RunSpec()))
    assert stats["p95_first_chunk_ms"] is None
    assert stats["p95_queue_ms"] is None
    assert percentile([], 0.95) is None


def test_nearest_rank_percentile_keeps_tail():
    assert percentile(range(1, 101), 0.95) == 95
    assert percentile([1, 2, 90], 0.95) == 90


def test_scenario_targets_are_seeded():
    p = PROFILES[Scenario.queue_pressure]
    assert timing(42, 3, p) == timing(42, 3, p)
    assert timing(42, 3, p) != timing(43, 3, p)


def test_restart_marks_unfinished_work_and_keeps_completed_runs(tmp_path):
    db = tmp_path / "runs.db"
    store = Store(db)
    active = Run(spec=RunSpec(), status="running")
    done = Run(spec=RunSpec(), status="completed")
    store.save(active)
    store.save(done)
    recovered = Store(db)
    assert recovered.get(active.id).status == "interrupted"
    assert recovered.get(done.id).status == "completed"
    assert recovered.get("missing") is None
