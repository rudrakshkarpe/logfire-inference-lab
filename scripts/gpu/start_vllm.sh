#!/usr/bin/env bash
set -euo pipefail
cd /workspace/inference-evidence
export PATH="/workspace/inference-evidence/.venv/bin:$PATH"
export VLLM_NO_USAGE_STATS=1
export DO_NOT_TRACK=1
export HF_HOME=/dev/shm/inference-model-cache
export OTEL_SERVICE_NAME=vllm-h100-serving
export OTEL_RESOURCE_ATTRIBUTES='deployment.environment.name=gpu-lab,observatory.engine=vllm,observatory.source=real-inference,observatory.capture_id=h100-gemma4-20260927'
export OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf
export OTEL_BSP_SCHEDULE_DELAY=1000
export OTEL_TRACES_SAMPLER=always_on
exec .venv/bin/vllm serve google/gemma-4-12B-it \
  --revision 707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7 \
  --host 127.0.0.1 --port 8000 \
  --language-model-only --dtype bfloat16 --max-model-len 8192 --max-num-seqs 4 \
  --gpu-memory-utilization 0.9 --enforce-eager --no-enable-prefix-caching \
  --otlp-traces-endpoint http://127.0.0.1:14318/v1/traces \
  --collect-detailed-traces all --enable-request-id-headers \
  --enable-per-request-metrics
