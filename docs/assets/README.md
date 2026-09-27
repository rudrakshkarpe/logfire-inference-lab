# Logfire capture provenance

## Laptop fixture captures

The original fixture images were captured from the signed-in Logfire UI in Brave on 2026-09-27. They show the `rudrakshkarpe/starter-project` project and the `observatory-stream` model. Browser tabs and the address bar were cropped out. Data, charts and labels were not redrawn or altered.

The GIF is a 10.8-second edited walkthrough of these captures, replacing the original 28-second slideshow. Each scene moves from the full view into magnified excerpts, with colored outlines marking the relevant totals, stage timings or exception. Queue and prefill scenes place two crops of the same rows side by side, bringing the stage names and timing column together. Captions describe the selected requests; they are not aggregate measurements. The original PNGs remain unchanged. This is not a continuous screen recording.

Rebuild it with `uv run --no-editable python scripts/build_walkthrough.py`. The script also writes full-resolution preview frames under the ignored `artifacts/walkthrough-preview/` directory. The GIF uses a shared color palette to reduce flicker and holds each focused view for two seconds.

| Capture | What it demonstrates |
|---|---|
| `model-overview.png` | Logfire's built-in AI Inference model overview: 120 calls, 5% exceptions |
| `queue-pressure.png` | Application-to-serving trace links and long admission waits |
| `slow-prefill.png` | The same layers with long prefill and negligible queueing |
| `interrupted-stream.png` | HTTP 200 followed by a streamed error and an OpenAI SDK exception |

The workload was generated locally; the requests, elapsed timings, exported traces and Logfire screens are real. Reported token counts are fixture units. No model weights or GPU engine were involved. The short run occupies one chart bucket, so the waterfall and saved SQL aggregates provide the more useful comparison than the time-series plots.

The images show a private project. They do not grant access to it. The model inventory's empty agents section is expected because the client makes direct model calls without an enclosing agent run. Earlier trial data uses a different model name and is excluded from the recorded model overview.

Trace IDs, local summaries and hosted aggregate results are in [`verified-run.json`](../evidence/verified-run.json). The captured workload window is **2026-09-27 06:59:22 to 07:00:00 UTC**, displayed locally as September 26 at 23:59 in the screenshots.

## Gemma H100 capture

`logfire-gemma-model.png` and `logfire-gemma-native-queue.png` are actual Logfire UI screenshots from September 27, 2026. Browser chrome was cropped from the top; dashboard values are unchanged. The model view includes 61 main requests and two smoke requests. The native span shows request `h100-gemma4-20260927-queue-pressure-028`. These images come from the separate real-engine run documented in [GPU validation](../gpu-validation.md); they are not frames from the earlier fixture walkthrough GIF.


`logfire-gemma-walkthrough.gif` is a 10.8-second, 1280 × 800 edited walkthrough of the two Gemma screenshots. It uses the same zoom treatment as the earlier fixture GIF: quick transitions, two-second focused holds, and colored outlines over unmodified excerpts. It shows model totals, application/engine parent links, queue wait, then prefill and decode. It is not a continuous recording. The 56-link caption comes from the verified run summary; selected-request timing captions describe `queue-pressure-028`, not a percentile.

Rebuild with `make gpu-gif` or `uv run --no-editable python scripts/build_gpu_walkthrough.py`. Four full-resolution focused previews are written to `artifacts/gpu-walkthrough-preview/`. The original screenshot PNGs remain available for static viewing and inspection.
