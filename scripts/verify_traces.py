"""Verify actual parent links between services in locally captured spans."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("trace_id")
args = parser.parse_args()
spans = []
for path in Path("data").glob("*-spans.jsonl"):
    spans.extend(json.loads(line) for line in path.read_text().splitlines())
spans = [s for s in spans if s["trace_id"] == args.trace_id and
         s["attributes"].get("logfire.span_type") != "pending_span"]
client = {s["span_id"] for s in spans if s["service"] == "inference-application"}
server = [s for s in spans if s["service"] == "inference-serving"]
links = [s for s in server if s["parent_id"] in client]
assert client and server and links, "No connected client/server spans found for this trace"
print(json.dumps({"trace_id": args.trace_id, "application_spans": len(client),
                  "serving_spans": len(server), "cross_process_parent_links": len(links)}, indent=2))
