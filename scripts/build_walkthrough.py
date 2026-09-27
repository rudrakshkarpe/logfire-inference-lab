"""Assemble a readable slideshow from actual, cropped Logfire UI captures."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

assets = Path("docs/assets")
slides = [
    ("model-overview", "1 / 4   AI Inference: 120 calls, six stream failures"),
    ("queue-pressure", "2 / 4   Queue pressure: admission wait dominates the request"),
    ("slow-prefill", "3 / 4   Slow prefill: preparation dominates, with almost no queue wait"),
    ("interrupted-stream", "4 / 4   Stream failure: HTTP 200 followed by a client exception"),
]
frames = []
for filename, caption in slides:
    source = Image.open(assets / f"{filename}.png").convert("RGB")
    source.thumbnail((1600, 900), Image.Resampling.LANCZOS)
    frame = Image.new("RGB", (1600, 910), "#101114")
    frame.paste(source, ((1600 - source.width) // 2, 54))
    ImageDraw.Draw(frame).text(
        (24, 14), caption, font=ImageFont.load_default(size=23), fill="#ffffff"
    )
    frames.append(frame.quantize(colors=128))
frames[0].save(
    assets / "logfire-walkthrough.gif",
    save_all=True,
    append_images=frames[1:],
    duration=7000,
    loop=0,
    optimize=True,
    disposal=2,
)
print(assets / "logfire-walkthrough.gif")
