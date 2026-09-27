import sqlite3
from pathlib import Path

from observatory.models import Run


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        for run in self.list():
            if run.status in {"pending", "running"}:
                run.status = "interrupted"
                run.failure = "Process stopped before this run completed."
                self.save(run)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def save(self, run: Run):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO runs VALUES (?, ?)", (run.id, run.model_dump_json()))

    def get(self, run_id: str) -> Run | None:
        with self.connect() as db:
            row = db.execute("SELECT body FROM runs WHERE id = ?", (run_id,)).fetchone()
        return Run.model_validate_json(row[0]) if row else None

    def list(self, limit: int = 100) -> list[Run]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT body FROM runs ORDER BY rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Run.model_validate_json(row[0]) for row in rows]
