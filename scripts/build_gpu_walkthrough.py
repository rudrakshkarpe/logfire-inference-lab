"""Build a short annotated walkthrough from the actual Gemma H100 Logfire captures."""

from pathlib import Path

from build_walkthrough import AMBER, ASSETS, CYAN, RED, Detail, Scene, build

SCENES = [
    Scene(
        "logfire-gemma-model",
        "Model",
        "Real Gemma inference, visible in Logfire",
        "63 calls. One expected invalid request.",
        "61 workload requests + two smoke tests on one H100.",
        CYAN,
        (
            Detail(
                (175, 185, 1640, 490),
                (36, 245, 1244, 497),
                "GEMMA 4 12B / VLLM 0.30.0 / ACTUAL MODEL DASHBOARD",
                (((185, 359, 625, 480), CYAN), ((650, 359, 1085, 480), RED)),
            ),
        ),
    ),
    Scene(
        "logfire-gemma-native-queue",
        "Trace",
        "Follow the application into the engine",
        "56 completed calls. 56 verified parent links.",
        "Application spans and native vLLM requests share the trace.",
        CYAN,
        (
            Detail(
                (130, 540, 1535, 900),
                (36, 220, 1244, 530),
                "APPLICATION PARENTS + NATIVE ENGINE CHILDREN",
                (((510, 583, 900, 674), CYAN),),
            ),
        ),
    ),
    Scene(
        "logfire-gemma-native-queue",
        "Queue",
        "Find where this request spent its time",
        "23.046 s waiting. 29.218 s total.",
        "Native engine timing attributes most of the delay to the queue.",
        AMBER,
        (
            Detail(
                (1590, 1080, 2970, 1400),
                (36, 235, 1244, 515),
                "SELECTED REQUEST / ENGINE TIMINGS IN SECONDS",
                (((1630, 1263, 2400, 1310), AMBER), ((1630, 1084, 2250, 1130), CYAN)),
            ),
        ),
    ),
    Scene(
        "logfire-gemma-native-queue",
        "Execution",
        "Separate queueing from model execution",
        "53 ms prefill. 6.108 s decode.",
        "These are the same request's native timings, not GPU kernel profiles.",
        CYAN,
        (
            Detail(
                (1590, 1080, 2970, 1400),
                (36, 235, 1244, 515),
                "SAME REQUEST / PREFILL AND DECODE",
                (((1630, 1218, 2540, 1264), CYAN), ((1630, 1128, 2460, 1177), CYAN)),
            ),
        ),
    ),
]

if __name__ == "__main__":
    build(
        SCENES,
        ASSETS / "logfire-gemma-walkthrough.gif",
        Path("artifacts/gpu-walkthrough-preview"),
        "ACTUAL LOGFIRE SCREENSHOTS  /  REAL GPU INFERENCE  /  EDITED ZOOM WALKTHROUGH",
    )
