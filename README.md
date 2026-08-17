# 知多丸式 挫折から学んだ効率的学習のすゝめ

中学数学 / 高校数学 / 高校英語 / 高校物理 / TOEIC を科目別に学べる静的学習ポータル。
学習法は『受験は要領』（和田秀樹）に学んだ「暗記数学・解法暗記・3回転復習・逆算計画」を軸に構成しています。

## 構成

```
index.html                 ポータルトップ（科目選択）
method.html                和田式メソッド（4本柱）
subjects/math-hs/          高校数学（公開中）
  index.html               単元一覧
  lessons/*.html           レッスン（解説動画つき）
subjects/math-jhs/         中学数学（準備中）
subjects/english-hs/       高校英語（準備中）
subjects/physics-hs/       高校物理（準備中）
subjects/toeic/            TOEIC（準備中）
videos/*.mp4               ナレーション付き解説動画
tools/make_video.py        解説動画の生成スクリプト
tools/lessons/*.json       動画のシーン定義（ナレーション原稿＋スライド）
```

ビルド不要の静的サイトです。ローカル確認は次のとおり。

```bash
python3 -m http.server 8000
# http://localhost:8000/
```

## 解説動画の作り方

シーン定義（JSON）にナレーション原稿とスライドの行を書き、スクリプトを実行すると
合成音声（edge-tts / ja-JP-NanamiNeural・やや低速）付きの mp4 が生成されます。

```bash
pip install edge-tts pillow          # ffmpeg も必要
python3 tools/make_video.py tools/lessons/quadratic_vertex.json videos/quadratic-vertex.mp4
```

シーン定義の各要素:

| キー | 説明 |
| --- | --- |
| `narration` | 読み上げ原稿。数式は「エックスの2乗」のように読み方で書く |
| `lines[].style` | `head` / `formula` / `text` / `note` |
| `lines[].active` | true のとき強調表示（そのシーンで新しく出た行に付ける） |
| `caption` | 画面下部の字幕（1行・40字程度まで） |
