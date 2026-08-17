"""解説動画（合成音声ナレーション付きmp4）生成スクリプト。

使い方:
    python3 tools/make_video.py tools/lessons/quadratic_vertex.json videos/quadratic-vertex.mp4

依存: edge-tts（合成音声）, ffmpeg（動画化）, Pillow（スライド描画）
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1280, 720
BG = (247, 249, 252)
INK = (29, 36, 48)
SUB = (91, 102, 117)
ACCENT = (20, 106, 95)
ACCENT_SOFT = (230, 242, 240)
CARD = (255, 255, 255)
LINE = (227, 232, 239)

FONT_PATH = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
VOICE = "ja-JP-NanamiNeural"
RATE = "-12%"
PITCH = "+8Hz"
TAIL_SEC = 0.7


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def rounded(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_slide(path: Path, title: str, subtitle: str, lines, caption: str) -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, WIDTH, 96], fill=CARD)
    d.rectangle([0, 96, WIDTH, 100], fill=ACCENT)
    d.text((56, 26), title, font=font(34), fill=INK)
    if subtitle:
        d.text((56, 66), subtitle, font=font(18), fill=SUB)

    top = 140
    rounded(d, [48, top, WIDTH - 48, HEIGHT - 132], 18, CARD, LINE, 2)

    y = top + 34
    for item in lines:
        style = item.get("style", "text")
        text = item["text"]
        active = item.get("active", False)
        if style == "formula":
            box_h = 62
            rounded(
                d,
                [84, y, WIDTH - 84, y + box_h],
                10,
                ACCENT_SOFT if active else (251, 252, 254),
                ACCENT if active else LINE,
                2,
            )
            d.text((108, y + 14), text, font=font(30), fill=INK)
            y += box_h + 18
        elif style == "head":
            d.rectangle([84, y + 6, 90, y + 34], fill=ACCENT)
            d.text((104, y), text, font=font(28), fill=ACCENT if active else INK)
            y += 52
        elif style == "note":
            d.text((104, y), text, font=font(23), fill=ACCENT if active else SUB)
            y += 42
        else:
            d.text((104, y), text, font=font(25), fill=INK if active else SUB)
            y += 44

    if caption:
        d.rectangle([0, HEIGHT - 96, WIDTH, HEIGHT], fill=(29, 36, 48))
        wrapped = caption
        d.text((56, HEIGHT - 68), wrapped, font=font(24), fill=(255, 255, 255))

    img.save(path)


def synth(text: str, out: Path) -> float:
    subprocess.run(
        [
            sys.executable, "-m", "edge_tts",
            "--voice", VOICE,
            f"--rate={RATE}",
            f"--pitch={PITCH}",
            "--text", text,
            "--write-media", str(out),
        ],
        check=True,
    )
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(out)],
        check=True, capture_output=True, text=True,
    )
    return float(probe.stdout.strip())


def build(spec_path: Path, out_path: Path) -> None:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    work = Path(tempfile.mkdtemp(prefix="lesson-video-"))
    segments = []

    for i, scene in enumerate(spec["scenes"]):
        png = work / f"s{i:02d}.png"
        mp3 = work / f"s{i:02d}.mp3"
        seg = work / f"s{i:02d}.mp4"

        draw_slide(
            png,
            scene.get("title", spec["title"]),
            scene.get("subtitle", spec.get("subtitle", "")),
            scene.get("lines", []),
            scene.get("caption", ""),
        )
        duration = synth(scene["narration"], mp3) + TAIL_SEC
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-i", str(mp3),
             "-c:v", "libx264", "-preset", "medium", "-tune", "stillimage",
             "-pix_fmt", "yuv420p", "-r", "25",
             "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
             "-af", f"apad=pad_dur={TAIL_SEC}",
             "-t", f"{duration:.3f}", "-shortest", str(seg)],
            check=True, capture_output=True,
        )
        segments.append(seg)

    listing = work / "list.txt"
    listing.write_text("".join(f"file '{s}'\n" for s in segments), encoding="utf-8")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out_path)],
        check=True, capture_output=True,
    )
    shutil.rmtree(work, ignore_errors=True)
    print(f"created {out_path}")


if __name__ == "__main__":
    build(Path(sys.argv[1]), Path(sys.argv[2]))
