"""Animate authentic Logfire captures with magnified excerpts and editorial highlights."""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path("docs/assets")
SIZE = (1280, 800)
BG = "#0b1018"
TEXT = "#f2f6ff"
MUTED = "#9aabc1"
CYAN = "#54dfd2"
AMBER = "#ffc269"
RED = "#ff797c"


def font(size):
    # Pillow's bundled font keeps generation portable across CI and local machines.
    return ImageFont.load_default(size=size)


@dataclass
class Detail:
    crop: tuple[int, int, int, int]
    target: tuple[int, int, int, int]
    label: str
    highlights: tuple[tuple[tuple[int, int, int, int], str], ...] = ()


@dataclass
class Scene:
    filename: str
    step: str
    title: str
    finding: str
    explanation: str
    color: str
    details: tuple[Detail, ...]


SCENES = [
    Scene(
        "model-overview",
        "Overview",
        "Start with the model overview",
        "120 calls. Six expected failures.",
        "The 5% exception rate matches the workload sent to Logfire.",
        CYAN,
        (
            Detail(
                (175, 190, 2030, 495),
                (36, 248, 1244, 447),
                "MODEL IDENTITY + REQUEST TOTALS",
                (((185, 357, 625, 482), CYAN), ((650, 357, 1085, 482), RED)),
            ),
        ),
    ),
    Scene(
        "queue-pressure",
        "Queue",
        "Follow the wait into the serving layer",
        "1.57 s in queue. 77.4 ms in prefill.",
        "This selected request spends most of its time waiting for admission.",
        AMBER,
        (
            Detail(
                (275, 690, 1445, 996),
                (36, 232, 918, 463),
                "REQUEST PATH",
                (((275, 870, 1445, 915), AMBER),),
            ),
            Detail(
                (2590, 690, 2990, 996),
                (942, 232, 1244, 463),
                "MATCHING TIMINGS",
                (((2590, 870, 2990, 915), AMBER), ((2590, 915, 2990, 958), CYAN)),
            ),
        ),
    ),
    Scene(
        "slow-prefill",
        "Prefill",
        "Now isolate slow prefill",
        "635 ms prefill. Just 73 microseconds in queue.",
        "Preparation dominates this request; admission is almost immediate.",
        CYAN,
        (
            Detail(
                (275, 943, 1445, 1249),
                (36, 232, 918, 463),
                "REQUEST PATH",
                (((275, 1158, 1445, 1203), CYAN),),
            ),
            Detail(
                (2590, 943, 2990, 1249),
                (942, 232, 1244, 463),
                "MATCHING TIMINGS",
                (((2590, 1158, 2990, 1203), CYAN), ((2590, 1114, 2990, 1158), AMBER)),
            ),
        ),
    ),
    Scene(
        "interrupted-stream",
        "Failure",
        "Inspect the stream, beyond HTTP status",
        "HTTP 200, then APIError",
        "Content arrived before the stream failed. Final usage is absent.",
        RED,
        (
            Detail(
                (275, 996, 1536, 1347),
                (36, 175, 1244, 511),
                "FAILED REQUEST + SUCCESSFUL HTTP RESPONSE",
                (((510, 998, 1536, 1043), RED), ((555, 1044, 1536, 1090), CYAN)),
            ),
            Detail(
                (1590, 935, 2990, 998),
                (36, 548, 1244, 602),
                "CLIENT EXCEPTION",
                (((1590, 935, 2990, 998), RED),),
            ),
        ),
    ),
]


def mapped(rect, source, target):
    sx = (target[2] - target[0]) / (source[2] - source[0])
    sy = (target[3] - target[1]) / (source[3] - source[1])
    return (
        target[0] + (rect[0] - source[0]) * sx,
        target[1] + (rect[1] - source[1]) * sy,
        target[0] + (rect[2] - source[0]) * sx,
        target[1] + (rect[3] - source[1]) * sy,
    )


def render(scene, index, progress):
    screenshot = Image.open(ASSETS / f"{scene.filename}.png").convert("RGB")
    frame = Image.new("RGB", SIZE, BG)
    preview = screenshot.copy()
    preview.thumbnail((1208, 438), Image.Resampling.LANCZOS)
    px, py = (SIZE[0] - preview.width) // 2, 151
    preview_box = (px, py, px + preview.width, py + preview.height)
    frame.paste(preview, (px, py))
    # Dim context as the unmodified detail crops expand out of their original positions.
    shade = Image.new("RGB", SIZE, BG)
    frame = Image.blend(frame, shade, 0.88 * progress)
    eased = 1 - (1 - progress) ** 3
    for detail in scene.details:
        start = mapped(detail.crop, (0, 0, *screenshot.size), preview_box)
        target = tuple(round(a + (b - a) * eased) for a, b in zip(start, detail.target))
        excerpt = screenshot.crop(detail.crop).resize(
            (target[2] - target[0], target[3] - target[1]), Image.Resampling.LANCZOS
        )
        frame.paste(excerpt, target[:2])
        if progress == 1:
            draw = ImageDraw.Draw(frame)
            draw.rectangle(target, outline="#42526b", width=1)
            draw.text((target[0], target[1] - 26), detail.label, font=font(16), fill=MUTED)
            for rect, color in detail.highlights:
                bounds = tuple(round(v) for v in mapped(rect, detail.crop, target))
                draw.rounded_rectangle(bounds, radius=5, outline=color, width=3)

    draw = ImageDraw.Draw(frame)
    draw.rectangle((0, 0, 1280, 137), fill=BG)
    draw.text((36, 18), "LOGFIRE INFERENCE LAB", font=font(16), fill=MUTED)
    draw.text((36, 51), scene.title, font=font(34), fill=TEXT)
    # A small four-step rail makes the loop's progression clear without a loading animation.
    for i, item in enumerate(SCENES):
        x = 36 + i * 305
        color = scene.color if i == index else "#253145"
        draw.rounded_rectangle((x, 110, x + 288, 114), radius=2, fill=color)
        draw.text((x, 122), f"0{i + 1}  {item.step}", font=font(14), fill=MUTED)

    draw.rectangle((0, 609, 1280, 800), fill=BG)
    draw.rounded_rectangle((36, 630, 42, 731), radius=3, fill=scene.color)
    draw.text((61, 638), scene.finding, font=font(32), fill=scene.color)
    draw.text((61, 689), scene.explanation, font=font(23), fill=TEXT)
    draw.text(
        (36, 763),
        "ACTUAL LOGFIRE CAPTURES  /  MAGNIFIED EXCERPTS  /  CONTROLLED WORKLOAD",
        font=font(14),
        fill=MUTED,
    )
    return frame


def main():
    frames, durations, focused = [], [], []
    for i, scene in enumerate(SCENES):
        frames.append(render(scene, i, 0))
        durations.append(160)
        for step in range(1, 7):
            frames.append(render(scene, i, step / 6))
            durations.append(60)
        focused.append(frames[-1])
        durations[-1] += 2000
        next_frame = render(SCENES[(i + 1) % len(SCENES)], (i + 1) % len(SCENES), 0)
        transition = Image.new("RGB", SIZE, BG)
        frames.extend(
            [
                Image.blend(focused[-1], transition, 0.65),
                Image.blend(next_frame, transition, 0.65),
                next_frame,
            ]
        )
        durations.extend([60, 60, 60])

    # Share one palette to avoid color flicker between zoom and hold frames.
    swatches = Image.new("RGB", (640, 400 * len(focused)))
    for i, frame in enumerate(focused):
        swatches.paste(frame.resize((640, 400)), (0, i * 400))
    palette = swatches.quantize(colors=192)
    encoded = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    destination = ASSETS / "logfire-walkthrough-zoom.gif"
    encoded[0].save(
        destination,
        save_all=True,
        append_images=encoded[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=1,
    )
    preview = Path("artifacts/walkthrough-preview")
    preview.mkdir(parents=True, exist_ok=True)
    for scene, frame in zip(SCENES, focused):
        frame.save(preview / f"{scene.filename}.png")
    print(f"{destination}: {sum(durations) / 1000:.1f}s, {destination.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
