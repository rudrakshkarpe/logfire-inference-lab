# Real-engine capture tools

These scripts capture a real OpenAI-compatible engine without changing the original laptop fixture. The current launch script pins vLLM's model revision and uses one H100 with `google/gemma-4-12B-it` in BF16, text-only mode, an 8,192-token context and at most four scheduled sequences. Eager execution and detailed tracing favor reliable startup and diagnosis; this configuration is not a throughput benchmark.

## Data path

```text
Local application --SSH tunnel--> vLLM on the GPU Pod
        |                              |
        | OTLP                         | OTLP over reverse SSH tunnel
        v                              v
Local archive receiver:14318
        |-- original OTLP protobuf batches + decoded JSON + checksum receipts
        `-- authenticated forwarding to the existing Logfire project
```

Both the inference endpoint and telemetry receiver bind to loopback. Logfire credentials stay on the local computer. Engine traces use vLLM's own instrumentation. The application passes W3C `traceparent` explicitly with each model call. `verify_capture.py` checks the server span's actual parent ID against the application span ID.

## Capture contents

- Immutable `.pb` OTLP export requests: canonical portable trace data.
- Decoded protobuf JSON for inspection. Use the `.pb` files for OTLP ingestion; generic protobuf JSON uses base64 IDs and is not the OTLP/JSON wire format.
- Receipt journal with checksums and HTTP forwarding results. New captures also record OTLP partial rejection counts or an invalid-response marker, since HTTP 200 alone does not guarantee acceptance.
- Request inputs, timestamped response chunks, token usage, finish reasons and exceptions.
- Per-request engine metrics when returned by the chosen vLLM version.
- Prometheus metrics before and after each workload scenario.
- GPU utilization, memory, power and temperature samples from `nvidia-smi`.
- Exact engine/client versions, model revision, launch script and startup logs.

A receiver HTTP 200 confirms local archive capture. The receipt records remote forwarding separately, and hosted SQL is used to verify ingestion. Failed forwards remain in the archive for deliberate replay.

## Workload

The smoke test runs two requests. The main workload runs 61 requests: baseline (8), queue pressure (32), long context (8), recovery (8), one deliberately invalid context-length request, and four intentionally closed streams. Valid completed requests require final token usage. Early-close requests retain missing usage as null rather than estimating generated token counts.

`ignore_eos=True` fixes output lengths for the controlled load. Thinking is disabled through the model's chat-template option. Prompts and generated tokens are real; queue pressure comes from actual requests contending for the configured four-sequence limit. Client timing includes the SSH/network path. Engine timing is captured separately. Prefill/decode values are engine request statistics, not a GPU kernel profile.

The recovery scenario returns to baseline concurrency; it does not change the server's scheduler configuration. Prefix caching is disabled to make the context-length comparison easier to interpret.

## Replay on another platform

The replay tool checks every payload against `receipts.jsonl` before inspection or transmission. Missing, extra or modified payloads fail verification before a network request is made. Keep the receipt journal with the protobuf files.

Inspect without sending anything:

```bash
uv run --no-editable python scripts/gpu/replay_otlp.py PATH_TO_ARCHIVE/otlp
```

To send to a chosen OTLP/HTTP receiver, set that platform's authentication and dataset headers in `OTLP_REPLAY_HEADERS_JSON`, then explicitly provide its complete traces endpoint:

```bash
uv run --no-editable python scripts/gpu/replay_otlp.py PATH_TO_ARCHIVE/otlp \
  --send --endpoint https://YOUR-RECEIVER/v1/traces
```

No backend is selected by default. This capture has not yet been ingested into Dash0. The preserved protobuf can be sent to an OTLP-compatible receiver after its endpoint, headers and timestamp acceptance window are configured.

For a demonstration that needs recent timestamps and distinct trace IDs, add `--shift-to-now --new-trace-ids`. A single timestamp offset preserves durations and inter-span timing. Trace-ID remapping preserves relationships and links. Replayed resources are marked `observatory.replayed=true`; original files remain unchanged. Replaying into the same project with original IDs may duplicate or overwrite records depending on the backend.

Prometheus snapshots and GPU CSV are separate evidence, not OTLP trace payloads. Replaying traces does not recreate live metrics or rerun the model. To reproduce the workload against another engine, adapt the pinned model configuration and rerun the saved prompts.

## Reproduce the GPU capture

Use a fresh output directory and a distinct capture ID for each run. The recorded setup used Linux with Python 3.12 and an H100. On the GPU host, create `/workspace/inference-evidence/.venv` and install the tested engine packages there:

```bash
uv venv --python python3.12 /workspace/inference-evidence/.venv
uv pip install --python /workspace/inference-evidence/.venv/bin/python \
  'vllm==0.30.0' 'opentelemetry-sdk==1.45.0' \
  'opentelemetry-exporter-otlp-proto-http==1.45.0' \
  'opentelemetry-exporter-otlp-proto-grpc==1.45.0' ninja
```

The capture's complete installed-package list is retained in its private evidence archive. The tested vLLM installation resolved PyTorch 2.13.0 and Transformers 5.17.0. Check model access and available memory/storage before launch. The recorded launch uses `/dev/shm` for the model cache and needs roughly 24 GB there for model weights, with additional room for downloads. Adapt that path if your host lacks sufficient shared memory.

On the laptop, use the repository's locked environment. Start the archive receiver in one terminal:

```bash
uv sync --locked --no-editable
uv run --no-editable python scripts/gpu/otlp_archive.py \
  --directory artifacts/gpu-runs/YOUR-RUN/otlp \
  --logfire-credentials .logfire/logfire_credentials.json
```

In another terminal, establish both SSH forwards using your own host, port and key:

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=20 \
  -p YOUR-SSH-PORT -i YOUR-SSH-KEY \
  -L 18000:127.0.0.1:8000 -R 14318:127.0.0.1:14318 USER@GPU-HOST
```

Copy `start_vllm.sh` to the GPU host, update its capture ID resource attribute, and run it there after creating the environment. Keep its output in a log. Wait for `/health` to return 200 through `http://127.0.0.1:18000`. Then run the smoke test and workload locally:

```bash
uv run --no-editable python scripts/gpu/capture_workload.py \
  --smoke --capture-id YOUR-RUN-smoke --output artifacts/gpu-runs/YOUR-RUN/smoke
uv run --no-editable python scripts/gpu/capture_workload.py \
  --capture-id YOUR-RUN --output artifacts/gpu-runs/YOUR-RUN/workload
uv run --no-editable python scripts/gpu/verify_capture.py artifacts/gpu-runs/YOUR-RUN
uv run --no-editable python scripts/gpu/verify_hosted.py artifacts/gpu-runs/YOUR-RUN
```

Hosted verification reads `.logfire/read_token.json` by default. That must contain a read token for the same project; see the repository's Logfire setup instructions. Allow native exports and hosted ingestion to finish before retrying a missing-span verification.

Collect engine logs, package versions and GPU samples separately; the workload client already captures Prometheus snapshots. Copy the complete evidence locally and verify its checksums before stopping the model. Keep the archive receiver and tunnels running through the engine's graceful shutdown so final exports can arrive. Finally, stop the receiver and tunnels. Stop or terminate the Pod separately when it is no longer needed.


## Offline checks

`make test` includes checks for corrupt/incomplete archives, missing versus zero token usage, partial OTLP rejections and unexpected workload outcomes. No GPU or Logfire credentials are needed for these tests.

`verify_capture.py` requires the planned request counts and expected outcomes, checks the exported parent links and token counts, and derives native queue/prefill/decode percentiles. Its scenario summaries include usage coverage: null token totals mean no final usage was returned, while partial sums count only requests with usage.

The September 27 raw capture is preserved unchanged. Its original manifest lists a nominal 128-token invalid-request plan, while the actual saved request and span show the 9,000-token override. The capture script now records 9,000 directly in future manifests. Existing forwarding receipts record HTTP status only; hosted SQL independently verified that run's ingestion.
