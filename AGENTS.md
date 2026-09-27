# Repository guidance

## Project and layout

Logfire Inference Lab traces streamed model requests across an application and
inference serving layer, using Pydantic Logfire as the investigation UI. Read
`README.md` before changing the integration. Do not add a separate frontend unless
requested.

Keep the real GPU capture and the laptop fixture distinct. The fixture uses
FastAPI, Pydantic and an OpenAI-compatible streaming API; it does not run model
weights. The GPU tools capture a real vLLM engine using explicit application spans
and native engine instrumentation. Neither path establishes support for untested
engines or versions.

- `src/observatory/`: fixture serving, client pipeline, telemetry, scenarios,
  settings, SQLite persistence and CLI.
- `scripts/gpu/`: real-engine launch, workload capture, OTLP archive/forwarding,
  replay and local/hosted verification. Read its `README.md` before GPU work.
- `scripts/verify_traces.py` and `scripts/verify_hosted.py`: fixture verification.
- `tests/`: core, fixture integration and GPU-tool tests that run without a GPU.
- `queries/`: Logfire SQL investigations; maintain their documented scope.
- `docs/`: integration, telemetry contract, operations and GPU validation.
- `docs/evidence/` and `docs/assets/`: public summaries and actual Logfire captures.
- `docs/drafts/`: proposed upstream documentation and maintainer follow-ups;
  these are drafts, not evidence that a message was posted or accepted upstream.

## Development and validation

Use Python 3.11+ and uv. CI currently checks Python 3.11 and 3.13. Keep
`pyproject.toml` and `uv.lock` consistent when deliberately changing dependencies.
Use the existing non-editable installation workflow:

```bash
uv sync --locked --no-editable
make lint
OBSERVATORY_EXPORT=false make test

# Narrow checks while iterating
OBSERVATORY_EXPORT=false uv run --no-editable pytest -q tests/test_gpu_tools.py
```

Follow `.github/workflows/ci.yml` and existing Ruff settings. Add regression tests
for behavior changes, including failure paths. Tests must not require credentials,
a rented GPU or hosted ingestion. Documentation-only changes need path/link and
diff checks; do not provision infrastructure for them. Report actual checks and
limitations rather than assuming local export proves hosted ingestion.

## Telemetry and evidence

- Keep the application span open through stream consumption. Preserve W3C trace
  context across the serving boundary and verify actual parent span IDs.
- Keep fixture stage spans separate from native vLLM timing attributes. Never
  invent engine spans or GPU observations to illustrate a desired result.
- Preserve missing final usage as null, distinct from zero and observed chunk
  counts. Intentional early closure does not prove server-side cancellation timing.
- Distinguish first protocol chunk, first content and engine TTFT. Preserve units,
  sample populations and timing boundaries. Do not subtract clocks across hosts
  or present short diagnostic scenarios as controlled performance benchmarks.
- Keep automatic OpenAI instrumentation findings separate from explicit manual
  span results. Rejection before generation does not test a mid-stream failure.
- Treat original captures as immutable. Verify checksums before replay; retain
  receipts, source identity and version/model configuration. Use canonical OTLP
  protobuf for export, not generic protobuf JSON as OTLP/JSON.
- Timestamp shifts and trace-ID remapping must preserve durations, parent links,
  events and attributes. Mark replays accurately; they do not rerun inference or
  recreate live GPU metrics.
- Distinguish archive acceptance, remote forwarding and hosted verification.
  Check partial rejection and actual hosted records before claiming ingestion.
  Update relevant documentation, SQL and public summaries when semantics change.

## Operations and privacy

Keep credentials, raw captures, prompts/completions and private response dumps out
of commits, terminal output and screenshots. Use ignored `.env`, `.logfire/`,
`data/` and `artifacts/` paths as documented. Keep published summaries reviewed and
limited to the measurements needed to support their claims.

Run hosted export, replay `--send`, GPU provisioning and deployment only within
the user's authorized task scope. Keep inference/archive endpoints on loopback
and Logfire credentials on the local computer when using SSH tunnels. Do not
blindly resend after a forwarding failure; inspect receipts and hosted records.
Back up and verify a capture before releasing its GPU. Keep receivers and tunnels
available for final exports during graceful engine shutdown. Stopping a model
process does not stop Pod billing; report infrastructure cleanup status accurately.

## Documentation, visuals and changes

Use actual Logfire screenshots. Zooms and highlights may guide attention but must
not change displayed telemetry. Preserve provenance in `docs/assets/README.md`
and identify edited walkthroughs accurately. Rebuild the GPU animation with
`make gpu-gif`; rebuild the fixture animation with
`uv run --no-editable python scripts/build_walkthrough.py`. Visually inspect
generated previews and keep static screenshots and relative links usable.

Preserve unrelated user changes and follow existing code patterns. Use focused,
conventional commits; do not manufacture commit history. New branches must have
descriptive names such as `fix/stream-usage` or `docs/capture-guide` and must not
include `codex`. Do not rename existing branches unless requested.

Keep public prose concise, specific and backed by evidence. Avoid em dashes.
Publish issue comments, PRs or maintainer messages only within the user's
authorization. `AGENTS.md` is the shared instruction file; keep `CLAUDE.md` as a
relative symlink to it, not a duplicate or a text file containing its name.
