"""Read back one demo's spans from Logfire without exposing query credentials."""

import argparse
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from logfire.query_client import LogfireQueryClient

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--input", type=Path, default=Path("artifacts/walkthrough.json"))
parser.add_argument("--credentials", type=Path, default=Path(".logfire/read_token.json"))
parser.add_argument("--output", type=Path, default=Path("artifacts/hosted-verification.json"))
args = parser.parse_args()
runs = [entry["run"] for entry in json.loads(args.input.read_text())]
trace_ids = [run["trace_id"] for run in runs]
if not runs or any(not re.fullmatch("[0-9a-f]{32}", tid) for tid in trace_ids):
    raise SystemExit("Expected completed runs with valid trace IDs")
credentials = json.loads(args.credentials.read_text())
start = min(datetime.fromisoformat(run["created_at"]) for run in runs) - timedelta(seconds=1)
results = {}
with LogfireQueryClient(
    read_token=credentials["token"], base_url=credentials["base_url"]
) as client:
    for name in ["scenario-latency", "stages", "requests"]:
        sql = Path(f"queries/{name}.sql").read_text()
        clause = "trace_id IN (" + ", ".join(f"'{tid}'" for tid in trace_ids) + ") AND "
        sql = sql.replace("WHERE ", "WHERE " + clause, 1)
        results[name] = client.query_json_rows(
            sql, min_timestamp=start, max_timestamp=datetime.now(UTC), limit=1000
        )
actual = {row["scenario"]: row for row in results["scenario-latency"]["rows"]}
for run in runs:
    row = actual.get(run["spec"]["scenario"], {})
    if (
        row.get("requests") != run["summary"]["completed"]
        or row.get("failed_requests") != run["summary"]["errors"]
    ):
        raise SystemExit(
            "Hosted counts differ from the local run. Check ingestion and project, then retry."
        )
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps({"trace_ids": trace_ids, "queries": results}, indent=2) + "\n")
print(
    f"Verified {sum(run['summary']['completed'] for run in runs)} requests "
    f"across {len(runs)} runs. Evidence: {args.output}"
)
