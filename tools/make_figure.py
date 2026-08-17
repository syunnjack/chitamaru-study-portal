"""図形だけを PNG に描き出すスクリプト（サイト掲載用）。

使い方:
    python3 tools/make_figure.py tools/lessons/pythagoras.json assets/figures/pythagoras.png

JSON は解説動画用の spec と同じ形式で、"figure" キー（または最初に figure を持つ scene）を使います。
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from make_video import BG, draw_figure

W, H = 720, 520


def main(spec_path: Path, out_path: Path) -> None:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    fig = spec.get("figure")
    if fig is None:
        fig = next(s["figure"] for s in spec["scenes"] if "figure" in s)

    img = Image.new("RGB", (W, H), BG)
    draw_figure(ImageDraw.Draw(img), (0, 0, W, H), fig)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    print(f"created {out_path}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
