"""YouTubeチャンネルの土台をまとめて作るスクリプト。

使い方:
    python3 tools/make_youtube_assets.py

youtube/videos.json をもとに、次を生成します。
    assets/youtube/banner.png        チャンネルアート（2560×1440・中央1546×423が安全領域）
    assets/youtube/icon.png          チャンネルアイコン（800×800）
    assets/youtube/thumbs/<slug>.png サムネイル（1280×720）
    youtube/metadata.md              全動画のタイトル・概要欄・タグ（コピペ用）
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from make_video import ACCENT, BG, CARD, INK, SUB, FONT_PATH, safe

ROOT = Path(__file__).resolve().parent.parent
DEEP = (12, 32, 46)
GOLD = (232, 178, 70)


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def bold(d: ImageDraw.ImageDraw, xy, text, size, fill, weight=2) -> None:
    d.text(xy, safe(text), font=font(size), fill=fill, stroke_width=weight, stroke_fill=fill)


def make_banner(spec, out: Path) -> None:
    w, h = 2560, 1440
    img = Image.new("RGB", (w, h), DEEP)
    d = ImageDraw.Draw(img)
    for i in range(h):  # 上から下へ、わずかに明るくするグラデーション
        t = i / h
        d.line([(0, i), (w, i)], fill=(int(12 + 18 * t), int(32 + 42 * t), int(46 + 44 * t)))
    d.rectangle([0, h // 2 + 180, w, h // 2 + 188], fill=ACCENT)

    # スマホで見える安全領域（中央 1546×423）に文字をすべて入れる。
    cx, top = w // 2, h // 2 - 170
    name = spec["channel"]["name"]
    tag = spec["channel"]["tagline"]
    tw = d.textlength(name, font=font(82))
    bold(d, (cx - tw / 2, top), name, 82, (255, 255, 255), 3)
    tw = d.textlength(tag, font=font(38))
    d.text((cx - tw / 2, top + 140), safe(tag), font=font(38), fill=GOLD)
    sub = "高校数学I・A ／ 高校受験数学 ／ 解説動画は全部無料"
    tw = d.textlength(sub, font=font(34))
    d.text((cx - tw / 2, top + 216), safe(sub), font=font(34), fill=(198, 212, 222))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"created {out}")


def make_icon(out: Path) -> None:
    s = 800
    img = Image.new("RGB", (s, s), DEEP)
    d = ImageDraw.Draw(img)
    d.ellipse([40, 40, s - 40, s - 40], outline=ACCENT, width=18)
    bold(d, (196, 214), "知多", 210, (255, 255, 255), 3)
    bold(d, (196, 424), "丸式", 210, GOLD, 3)
    img.save(out)
    print(f"created {out}")


def make_thumb(video, badge, out: Path) -> None:
    w, h = 1280, 720
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 150], fill=DEEP)
    bold(d, (56, 46), badge, 56, (255, 255, 255), 2)
    d.text((w - 620, 62), safe("知多丸の落ちこぼれ救済チャンネル"), font=font(36), fill=(198, 212, 222))
    d.rectangle([0, 150, w, 160], fill=ACCENT)

    lines = video["thumb"]
    y = 226
    for i, text in enumerate(lines):
        size = 84 if i == 0 else (64 if i == 1 else 72)
        color = INK if i == 0 else (SUB if i == 1 else ACCENT)
        if i == len(lines) - 1:
            tw = d.textlength(safe(text), font=font(size))
            d.rounded_rectangle([48, y - 14, 48 + tw + 48, y + size + 22], 16, (230, 242, 240), ACCENT, 4)
            bold(d, (72, y), text, size, ACCENT, 2)
        else:
            bold(d, (56, y), text, size, color, 2)
        y += size + 34

    d.rectangle([0, h - 74, w, h], fill=DEEP)
    d.text((56, h - 58), safe("チャンネル登録で全動画が無料・やさしい音声解説"), font=font(34), fill=(255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def make_metadata(spec, out: Path) -> None:
    ch = spec["channel"]
    pls = {p["id"]: p for p in spec["playlists"]}
    lines = [
        f"# {ch['name']}／全動画のコピペ用メタデータ",
        "",
        "`tools/make_youtube_assets.py` が `youtube/videos.json` から自動生成します（手で編集しないでください）。",
        "",
        "## 共通のしめ（各概要欄の末尾に貼る）",
        "",
        "```",
        "◆このチャンネルの方針",
        "・5分考えて分からない問題は、答えを見る（考え込む時間は勉強時間ではない）",
        "・解けなかった問題を3回転（①書き写す ②翌日に何も見ずに ③1週間後に方針を30秒で言う）",
        "・満点を目指さず、合格点から逆算する",
        "",
        f"◆解説ページ（無料・全公開）：{ch['site']}",
        "◆チャンネル登録すると、新しい解説動画がすべて無料で見られます。",
        "```",
        "",
    ]
    for pl in spec["playlists"]:
        lines += [f"## 再生リスト：{pl['name']}", ""]
        for v in [x for x in spec["videos"] if x["playlist"] == pl["id"]]:
            lines += [
                f"### {v['title']}",
                "",
                f"- ファイル：`videos/{v['slug']}.mp4`",
                f"- サムネイル：`assets/youtube/thumbs/{v['slug']}.png`",
                f"- 解説ページ：{ch['site']}{v['page']}",
                "",
                "```",
                v["hook"],
                v["point"],
                "",
                f"解説ページ：{ch['site']}{v['page']}",
                "チャンネル登録すると、新しい解説動画がすべて無料で見られます。",
                "",
                pl["hashtags"],
                "```",
                "",
            ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"created {out}")


LANDING_HEAD = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube｜知多丸の落ちこぼれ救済チャンネル</title>
<meta name="description" content="知多丸の落ちこぼれ救済チャンネルの解説動画（高校数学I・A／高校受験数学）を全部無料で公開。チャンネル登録すると新しい動画がすべて届きます。">
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="site">
  <div class="wrap">
    <a class="brand" href="index.html">知多丸式 挫折から学んだ効率的学習のすゝめ<small>要領で学ぶ、科目別学習ポータル</small></a>
    <nav class="site">
      <a href="method.html">和田式メソッド</a>
      <a href="youtube.html">YouTube</a>
      <a href="subjects/math-hs/index.html">高校数学</a>
      <a href="subjects/math-exam/index.html">高校受験数学</a>
      <a href="subjects/math-jhs/index.html">中学数学</a>
      <a href="subjects/english-hs/index.html">高校英語</a>
      <a href="subjects/physics-hs/index.html">高校物理</a>
      <a href="subjects/toeic/index.html">TOEIC</a>
    </nav>
  </div>
</header>

<div class="wrap breadcrumb"><a href="index.html">トップ</a> ／ YouTube</div>

<main class="wrap">
  <h1>知多丸の落ちこぼれ救済チャンネル</h1>
  <div class="panel accent">
    <p><strong>難関大学に合格して、錯覚資産を手に入れて、一流企業に入社しよう！</strong></p>
    <p>解説動画は<strong>すべて無料</strong>です。チャンネル登録をすると、新しい動画と続きのシリーズがすべて自動で届きます。</p>
CHANNEL_CTA
  </div>

  <div class="panel note">
    <p>1本1型です。<strong>問題を5分だけ考える → 動画で型を確認する → 翌日、何も見ずに解き直す</strong>。この順で使ってください。</p>
  </div>
"""

LANDING_FOOT = """
  <h2>この順でやれば単元が終わります</h2>
  <div class="panel">
    <ol>
      <li>高校数学は「2次関数 → 図形と計量 → データの分析 → 場合の数 → 整数」の順。</li>
      <li>高校受験数学は「計算の工夫 → 図形 → 円 → 因数分解 → 軌跡」の順。</li>
      <li>解けなかった問題だけ3回転（書き写す → 翌日 → 1週間後に方針を30秒）。</li>
    </ol>
  </div>
</main>

<footer class="site">
  <div class="wrap">知多丸式 挫折から学んだ効率的学習のすゝめ</div>
</footer>
</body>
</html>
"""


def make_landing(spec, out: Path) -> None:
    """サイト側の YouTube 誘導ページを書き出す（videos.json が唯一の情報源）。"""
    url = spec["channel"].get("channel_url", "")
    if url:
        cta = f'    <p><a class="cta" href="{url}">▶ チャンネル登録して全部見る</a></p>'
    else:
        cta = (
            "    <p>チャンネルの開設準備中です。下の解説ページでは、同じ内容をすでに無料で見られます。</p>"
        )
    parts = [LANDING_HEAD.replace("CHANNEL_CTA", cta)]
    for pl in spec["playlists"]:
        parts.append(f"\n  <h2>{pl['name']}</h2>\n  <div class=\"cards\">\n")
        for v in [x for x in spec["videos"] if x["playlist"] == pl["id"]]:
            parts.append(
                f'    <a class="card" href="{v["page"]}">\n'
                f'      <img src="assets/youtube/thumbs/{v["slug"]}.png" alt="{v["title"]}" '
                f'style="width:100%;height:auto;border-radius:10px;border:1px solid var(--line)">\n'
                f'      <h3>{v["title"]}</h3>\n'
                f'      <p>{v["hook"]}</p>\n'
                f"    </a>\n"
            )
        parts.append("  </div>\n")
    parts.append(LANDING_FOOT)
    out.write_text("".join(parts), encoding="utf-8")
    print(f"created {out}")


def main() -> None:
    spec = json.loads((ROOT / "youtube/videos.json").read_text(encoding="utf-8"))
    badges = {p["id"]: p["badge"] for p in spec["playlists"]}
    make_banner(spec, ROOT / "assets/youtube/banner.png")
    make_icon(ROOT / "assets/youtube/icon.png")
    for v in spec["videos"]:
        make_thumb(v, badges[v["playlist"]], ROOT / f"assets/youtube/thumbs/{v['slug']}.png")
    print(f"created {len(spec['videos'])} thumbnails")
    make_metadata(spec, ROOT / "youtube/metadata.md")
    make_landing(spec, ROOT / "youtube.html")


if __name__ == "__main__":
    main()
