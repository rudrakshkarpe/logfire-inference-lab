"""Read back captured client/engine spans from Logfire and verify parent links."""

import argparse
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from logfire.query_client import LogfireQueryClient

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("directory", type=Path)
parser.add_argument("--credentials", type=Path, default=Path(".logfire/read_token.json"))
args = parser.parse_args()
requests = json.loads((args.directory / "workload/request-index.json").read_text())
manifest = json.loads((args.directory / "workload/manifest.json").read_text())
ids = sorted({r["trace_id"] for r in requests})
assert ids and all(re.fullmatch("[0-9a-f]{32}", tid) for tid in ids)
where = ",".join(f"'{tid}'" for tid in ids)
sql = f"""
SELECT trace_id, span_id, parent_span_id, service_name, span_name, duration,
       is_exception, exception_type,
       attributes->>'observatory.scenario' AS scenario,
       attributes->>'observatory.request_id' AS request_id,
       attributes->>'gen_ai.latency.time_in_queue' AS engine_queue_s,
       attributes->>'gen_ai.latency.time_in_model_prefill' AS engine_prefill_s,
       attributes->>'gen_ai.latency.time_in_model_decode' AS engine_decode_s
FROM records
WHERE trace_id IN ({where}) AND kind='span'
  AND (attributes->>'gen_ai.operation.name' = 'chat' OR span_name='llm_request')
ORDER BY start_timestamp
"""
credentials = json.loads(args.credentials.read_text())
with LogfireQueryClient(
    read_token=credentials["token"], base_url=credentials["base_url"]
) as client:
    result = client.query_json_rows(
        sql,
        min_timestamp=datetime.fromisoformat(manifest["started_at"]) - timedelta(minutes=1),
        max_timestamp=datetime.now(UTC),
        limit=1000,
    )
(args.directory / "hosted-records.json").write_text(json.dumps(result, indent=2))
(args.directory / "hosted-verification.sql").write_text(sql)
rows = result["rows"]
linked = 0
for request in requests:
    clients = [
        r
        for r in rows
        if r["trace_id"] == request["trace_id"] and r["span_id"] == request["span_id"]
    ]
    assert len(clients) == 1, f"Client record missing: {request['request_id']}"
    children = [
        r
        for r in rows
        if r["trace_id"] == request["trace_id"]
        and r["parent_span_id"] == request["span_id"]
        and r["span_name"] == "llm_request"
    ]
    if request["status"] == "ok":
        assert len(children) == 1, f"Engine record missing: {request['request_id']}"
    if children:
        linked += 1
    if request["status"] == "error":
        assert clients[0]["is_exception"]
summary = {
    "requests_verified": len(requests),
    "engine_parent_links_verified": linked,
    "records": len(rows),
    "trace_ids": ids,
    "checked_at": datetime.now(UTC).isoformat(),
}
(args.directory / "hosted-verification.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
