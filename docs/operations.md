# Operations and troubleshooting

## Configuration

Copy `.env.example` once and edit the ignored `.env`. Shell environment variables take precedence.

| Setting | Default | Purpose |
|---|---|---|
| `OBSERVATORY_EXPORT` | `false` | Enable hosted telemetry export in both processes |
| `LOGFIRE_TOKEN` | unset | Optional project write token; otherwise use local CLI credentials |
| `LOGFIRE_BASE_URL` | US Logfire endpoint | Regional telemetry destination |
| `OBSERVATORY_PROJECT_URL` | unset | UI link prefix only |
| `OBSERVATORY_PORT` | `8877` | Serving process listen port |
| `OBSERVATORY_SERVING_URL` | `http://127.0.0.1:8877/v1` | Client's serving endpoint |
| `OBSERVATORY_CAPTURE_TRACES` | `true` | Write local redacted JSONL for parent-link verification |
| `OBSERVATORY_DB` | `data/observatory.db` | Local run store |

Run `observatory doctor` after starting the service. It checks local storage, configured credential presence and the health endpoint. It does not test token validity or prove hosted ingestion. Use hosted verification for that.

Restart the serving process after changing `.env`; a process does not reload its settings on every request. Changing the serving port also requires changing the client URL. Container compose uses port 8877 explicitly.

## Common symptoms

| Symptom | Check or resolution |
|---|---|
| `Address already in use` | Stop this project's other serving process or choose an unused port. Do not terminate an unrelated service. |
| Connection refused | Start `observatory serve`, then run `observatory doctor`; check both port and base URL. |
| No records in Logfire | Enable export in both processes, match project credentials and region, restart the server, then inspect export errors and the selected UI time range. |
| Only one service is visible | The application and server may use different project credentials, or the server may still be running with export disabled. |
| Trace continuity error | Verify HTTP instrumentation, trusted context extraction and that the endpoint is the included fixture. A generic engine will not return the fixture's trace ID extension. |
| Model overview counts differ | Filter `observatory-stream` and the correct experiment window. Earlier trial data used `observatory-chat`. Avoid adding automatic OpenAI instrumentation on top of the explicit GenAI span. |
| SQL returns fewer request rows | The saved request query limits to 120. The Query API has its own limit; the verification script explicitly requests 1,000. |
| HTTP 200 and a red exception | Expected for an error received after response headers. Inspect the client stream traceback, not only HTTP status. |
| Token counts missing on failures | Expected. No final usage record was received. `observed_chunks` records partial progress separately. |
| Blank or sparse model charts | This demo is a short burst and can occupy one chart bucket. Inspect the summary cards, request waterfalls and SQL aggregates. |
| Empty agents section | Expected for direct OpenAI-client calls. This project does not wrap them in a Pydantic AI agent. |
| `ModuleNotFoundError: observatory` after an editable install | Use the documented `uv sync --locked --no-editable` and `uv run --no-editable` commands. |

If you edit source and want to be certain the installed wheel is refreshed:

```bash
uv sync --locked --no-editable --reinstall-package logfire-inference-observatory
```

## Container workflow

The default Docker image contains the package and locked production dependencies. It runs as a non-root user, exposes only the serving endpoint, and keeps generated evidence in `/app/data`. Compose mounts a named volume there.

For a local-only run, leave `OBSERVATORY_EXPORT=false`. For hosted export, set a write token in `.env` before starting the container. The container deliberately does not mount the host's `.logfire/` directory or global auth file. Keep `LOGFIRE_BASE_URL` aligned with the token region.

```bash
docker compose config --quiet
docker compose up --build
# In another terminal:
uv run --no-editable observatory doctor
uv run --no-editable python scripts/demo.py
# After stopping the workload:
docker compose down
```

`docker compose down` keeps the named evidence volume. When the server runs in a container, its JSONL file is in that volume, while the application's capture is on the host. The local `verify_traces.py` command needs both captures under the host's `data/` directory; copy the server file out with `docker compose cp serving:/app/data/inference-serving-spans.jsonl data/inference-serving-spans.jsonl` before stopping the container. The hosted verification command works without copying local traces.

This is a single-worker reference service. Admission pools are process-local. There is no authentication, shared scheduler or production rate limiter. Loopback binding keeps the default lab private to the machine.

## Repeatable checks

```bash
make lint
make test
uv run --no-editable python scripts/verify_traces.py YOUR_TRACE_ID
uv run --no-editable python scripts/verify_hosted.py
```

The integration tests start a separate fixture process on a dynamically chosen local port, disable hosted export, and use isolated temporary storage. They exercise all five scenarios through actual HTTP streaming. Timing assertions compare broad differences between scenarios instead of expecting exact wall-clock numbers.

The recorded validation on 2026-09-27 included:

- 14 passing tests on host Python 3.11, including one complete model span per request and two failed streams out of eight in the fault scenario.
- Ruff lint and formatting checks.
- A built Docker image on Python 3.13, with a successful health request and a stream consumed through `[DONE]` on a temporary loopback port.
- Hosted SQL verification of 120 requests and six exceptions across the five recorded traces.
- Actual Logfire UI inspection and screenshot capture.

After publication, [GitHub Actions run 36302500168](https://github.com/rudrakshkarpe/logfire-inference-lab/actions/runs/36302500168) passed on both Python 3.11 and 3.13. Both jobs ran lint, formatting checks and the full test suite.

## Handling evidence

Raw local data and credentials remain in ignored paths. The checked-in evidence contains only selected workload summaries, trace IDs, hosted aggregates and cropped UI captures. Review new screenshots before committing them because tracebacks can include local paths and project names. The current captures include this project's identity and local source path, but no credentials.

Do not backdate experiments or alter captured dashboard values. When changing instrumentation, generate a new run and update the evidence manifest and screenshots together. Keep the provenance and measurement units visible, especially when moving from fixture output to a hardware-backed engine.
