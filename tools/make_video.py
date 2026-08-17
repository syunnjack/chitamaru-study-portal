"""解説動画（合成音声ナレーション付きmp4）生成スクリプト。

使い方:
    python3 tools/make_video.py tools/lessons/quadratic_vertex.json videos/quadratic-vertex.mp4

依存: edge-tts（合成音声）, ffmpeg（動画化）, Pillow（スライド描画）
"""

import json
import shutil
import math
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


# IPA ゴシックが持つ上付き文字は ¹²³ だけ。それ以外は豆腐（□）になるので
# 「^2」「^(n+1)」の形に落とす。下付きは1つも持たないので普通の文字にする。
SUPERSCRIPTS = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹ⁿ⁺⁻", "0123456789n+-"))
SUBSCRIPTS = dict(zip("₀₁₂₃₄₅₆₇₈₉ₙ₊₋", "0123456789n+-"))
FONT_HAS_SUPERSCRIPT = set("¹²³")


def safe(text: str) -> str:
    out = []
    i = 0
    while i < len(text):
        for table, marker in ((SUPERSCRIPTS, "^"), (SUBSCRIPTS, "")):
            if text[i] in table:
                run = ""
                while i < len(text) and text[i] in table:
                    run += text[i]
                    i += 1
                plain = "".join(table[c] for c in run)
                if table is SUPERSCRIPTS and set(run) <= FONT_HAS_SUPERSCRIPT:
                    out.append(run)  # そのまま表示できる
                elif "+" in plain or "-" in plain:
                    out.append(f"{marker}({plain})")
                else:
                    out.append(marker + plain)
                break
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def rounded(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _project(points, box):
    """図形の座標（数学の向き）を、描画領域 box にはめこむ変換を返す。"""
    x0, y0, x1, y1 = box
    xs = [p[0] for p in points.values()]
    ys = [p[1] for p in points.values()]
    w = max(xs) - min(xs) or 1.0
    h = max(ys) - min(ys) or 1.0
    pad = 64
    scale = min((x1 - x0 - 2 * pad) / w, (y1 - y0 - 2 * pad) / h)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2

    def to_px(p):
        return (mx + (p[0] - cx) * scale, my - (p[1] - cy) * scale)

    return to_px, scale


def draw_figure(d: ImageDraw.ImageDraw, box, fig) -> None:
    """図形（三角形・線分・直角記号・長さ・角度）を描く。

    fig の例:
        {"points": {"A": [0, 3], "B": [0, 0], "C": [4, 0]},
         "polygons": [["A", "B", "C"]],
         "segments": [["B", "M"]],
         "right_angles": [["A", "B", "C"]],
         "lengths": [{"between": ["A", "B"], "text": "3"}],
         "angles": [{"at": "A", "from": "B", "to": "C", "text": "60°"}],
         "labels": [{"at": "A", "text": "A", "dx": -28, "dy": -34}],
         "circles": [{"center": "O", "through": "A"}],
         "shaded": [{"center": "O", "from": "A", "to": "B", "apex": "H"}],
         "curves": [[[-2, 4], [-1, 1], [0, 0], [1, 1], [2, 4]]],
         "axes": true}

    curves は数学座標の点列で、そのまま折れ線として描く（放物線などのグラフ用）。
    axes を true にすると、図の範囲いっぱいに x 軸・y 軸を引く。

    circles は中心と円周上の1点で指定する。shaded は「頂点 apex ＋ 弦の両端 from, to
    を結び、from から to への短いほうの弧でふたをした領域」を塗る。
    """
    pts = {k: (float(v[0]), float(v[1])) for k, v in fig["points"].items()}
    circles = [
        (pts[c["center"]], math.dist(pts[c["center"]], pts[c["through"]]))
        for c in fig.get("circles", [])
    ]

    curves = [[(float(p[0]), float(p[1])) for p in c] for c in fig.get("curves", [])]

    bounds = dict(pts)
    for i, curve in enumerate(curves):
        for j, p in enumerate(curve):
            bounds[f"_v{i}_{j}"] = p
    for i, (o, r) in enumerate(circles):
        bounds[f"_c{i}min"] = (o[0] - r, o[1] - r)
        bounds[f"_c{i}max"] = (o[0] + r, o[1] + r)
    to_px, scale = _project(bounds, box)
    P = {k: to_px(v) for k, v in pts.items()}

    def arc_points(o, r, p, q, n=64):
        """中心 o の円上で、p から q への短いほうの弧をなぞる点列（数学座標）。"""
        a0 = math.atan2(p[1] - o[1], p[0] - o[0])
        a1 = math.atan2(q[1] - o[1], q[0] - o[0])
        span = (a1 - a0) % (2 * math.pi)
        if span > math.pi:
            a0, a1, span = a1, a0, 2 * math.pi - span
        return [
            (o[0] + r * math.cos(a0 + span * i / n), o[1] + r * math.sin(a0 + span * i / n))
            for i in range(n + 1)
        ]

    if fig.get("axes"):
        xs = [p[0] for p in bounds.values()]
        ys = [p[1] for p in bounds.values()]
        d.line([to_px((min(xs), 0)), to_px((max(xs), 0))], fill=SUB, width=2)
        d.line([to_px((0, min(ys))), to_px((0, max(ys)))], fill=SUB, width=2)

    for item in fig.get("shaded", []):
        o, r = circles[item.get("circle", 0)]
        arc = arc_points(o, r, pts[item["from"]], pts[item["to"]])
        d.polygon([P[item["apex"]]] + [to_px(p) for p in arc], fill=ACCENT_SOFT)

    for o, r in circles:
        c = to_px(o)
        rp = r * scale
        d.ellipse([c[0] - rp, c[1] - rp, c[0] + rp, c[1] + rp], outline=INK, width=3)

    for poly in fig.get("polygons", []):
        d.polygon([P[k] for k in poly], fill=(255, 255, 255), outline=None)
        seq = [P[k] for k in poly] + [P[poly[0]]]
        d.line(seq, fill=INK, width=3, joint="curve")

    for curve in curves:
        d.line([to_px(p) for p in curve], fill=INK, width=3, joint="curve")

    for seg in fig.get("segments", []):
        a, b = P[seg[0]], P[seg[1]]
        d.line([a, b], fill=ACCENT, width=3)

    for tri in fig.get("right_angles", []):
        a, v, c = (P[k] for k in tri)
        size = 22.0

        def unit(p, q):
            dx, dy = q[0] - p[0], q[1] - p[1]
            n = (dx * dx + dy * dy) ** 0.5 or 1.0
            return dx / n, dy / n

        u1, u2 = unit(v, a), unit(v, c)
        p1 = (v[0] + u1[0] * size, v[1] + u1[1] * size)
        p2 = (v[0] + u2[0] * size, v[1] + u2[1] * size)
        p3 = (p1[0] + u2[0] * size, p1[1] + u2[1] * size)
        d.line([p1, p3, p2], fill=ACCENT, width=3)

    f_lab = font(26)
    for item in fig.get("lengths", []):
        a, b = P[item["between"][0]], P[item["between"][1]]
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        dx = item.get("dx", 0)
        dy = item.get("dy", 0)
        d.text((mid[0] + dx - 10, mid[1] + dy - 14), safe(item["text"]), font=f_lab, fill=ACCENT)

    for item in fig.get("angles", []):
        v = P[item["at"]]
        r = item.get("r", 46)
        d.arc([v[0] - r, v[1] - r, v[0] + r, v[1] + r],
              start=item.get("start", 0), end=item.get("end", 90),
              fill=ACCENT, width=3)
        d.text((v[0] + item.get("dx", 0), v[1] + item.get("dy", 0)),
               safe(item["text"]), font=font(24), fill=ACCENT)

    for item in fig.get("labels", []):
        v = P[item["at"]]
        d.text((v[0] + item.get("dx", -12), v[1] + item.get("dy", -36)),
               safe(item["text"]), font=font(28), fill=INK)
        d.ellipse([v[0] - 4, v[1] - 4, v[0] + 4, v[1] + 4], fill=INK)


def draw_slide(path: Path, title: str, subtitle: str, lines, caption: str, figure=None) -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, WIDTH, 96], fill=CARD)
    d.rectangle([0, 96, WIDTH, 100], fill=ACCENT)
    d.text((56, 26), safe(title), font=font(34), fill=INK)
    if subtitle:
        d.text((56, 66), safe(subtitle), font=font(18), fill=SUB)

    top = 140
    rounded(d, [48, top, WIDTH - 48, HEIGHT - 132], 18, CARD, LINE, 2)

    right = WIDTH - 84
    if figure:
        right = 660
        draw_figure(d, (690, top + 20, WIDTH - 72, HEIGHT - 152), figure)

    y = top + 34
    for item in lines:
        style = item.get("style", "text")
        text = safe(item["text"])
        active = item.get("active", False)
        if style == "formula":
            box_h = 62
            rounded(
                d,
                [84, y, right, y + box_h],
                10,
                ACCENT_SOFT if active else (251, 252, 254),
                ACCENT if active else LINE,
                2,
            )
            d.text((108, y + 14), text, font=font(26 if figure else 30), fill=INK)
            y += box_h + 18
        elif style == "head":
            d.rectangle([84, y + 6, 90, y + 34], fill=ACCENT)
            d.text((104, y), text, font=font(28), fill=ACCENT if active else INK)
            y += 52
        elif style == "note":
            d.text((104, y), text, font=font(21 if figure else 23), fill=ACCENT if active else SUB)
            y += 42
        else:
            d.text((104, y), text, font=font(25), fill=INK if active else SUB)
            y += 44

    if caption:
        d.rectangle([0, HEIGHT - 96, WIDTH, HEIGHT], fill=(29, 36, 48))
        wrapped = safe(caption)
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
            scene.get("figure", spec.get("figure")),
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
