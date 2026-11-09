"""Generate crawl metadata, lesson transcripts, and a sitemap for the static portal."""

import argparse
import html
import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://gyosei-yosou.jp/study-portal/"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
SEO_MARKER = "<!-- generated SEO metadata -->"
SEO_END_MARKER = "<!-- /generated SEO metadata -->"
TRANSCRIPT_MARKER = '<section class="video-transcript"'


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = []
        self.h1 = []
        self._active_text = None
        self._text_depth = 0
        self.video_src = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "video" and not self.video_src:
            self.video_src = attributes.get("src")
        if tag in {"title", "h1"}:
            if self._active_text is None:
                self._active_text = self.title if tag == "title" else self.h1
                self._text_depth = 1
            else:
                self._text_depth += 1
        elif self._active_text is not None and tag not in {"meta", "link", "img"}:
            self._text_depth += 1

    def handle_endtag(self, tag):
        if self._active_text is None:
            return
        if tag in {"title", "h1"} and self._text_depth == 1:
            self._active_text = None
            self._text_depth = 0
        else:
            self._text_depth = max(1, self._text_depth - 1)

    def handle_data(self, data):
        if self._active_text is not None:
            self._active_text.append(data)


def parse_page(source):
    parser = PageParser()
    parser.feed(source)
    title_match = re.search(r"<title\b[^>]*>(.*?)</title>", source, re.I | re.S)
    description_match = re.search(
        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']\s*/?>',
        source,
        re.I | re.S,
    )
    return (
        " ".join("".join(parser.title).split())
        or (html.unescape(title_match.group(1)).strip() if title_match else ""),
        " ".join("".join(parser.h1).split()),
        html.unescape(description_match.group(1)).strip()
        if description_match
        else "",
        parser.video_src,
    )


def page_url(base_url, relative_path):
    if relative_path.as_posix() == "index.html":
        return base_url
    if relative_path.name == "index.html":
        return base_url.rstrip("/") + "/" + quote(
            relative_path.parent.as_posix(), safe="/-._~"
        ) + "/"
    path = quote(relative_path.as_posix(), safe="/-._~")
    return base_url.rstrip("/") + "/" + path


def h1_for(path):
    source = path.read_text(encoding="utf-8")
    _, heading, _, _ = parse_page(source)
    return heading


def lesson_breadcrumbs(path, base_url, heading):
    items = [{"name": "知多丸式 学習ポータル", "url": base_url}]
    if path.parts[0] == "subjects" and len(path.parts) >= 3:
        subject_index = ROOT / path.parts[0] / path.parts[1] / "index.html"
        subject_name = h1_for(subject_index) if subject_index.exists() else path.parts[1]
        subject_relative = Path(path.parts[0]) / path.parts[1] / "index.html"
        items.append(
            {
                "name": subject_name,
                "url": page_url(base_url, subject_relative),
            }
        )
    if path.parts[0] == "subjects" and "lessons" in path.parts:
        heading = heading or path.stem
        current_url = page_url(base_url, path)
        if not items or items[-1]["url"] != current_url:
            items.append({"name": heading, "url": current_url})
    elif path.parts[0] != "subjects" and path != Path("index.html"):
        current_url = page_url(base_url, path)
        items.append({"name": heading or path.parent.name, "url": current_url})
    return items


def video_narrations(video_src):
    if not video_src:
        return []
    filename = Path(urlsplit(html.unescape(video_src)).path).name
    if not filename.lower().endswith(".mp4"):
        return []
    video_path = ROOT / "videos" / filename
    if not video_path.is_file():
        return []
    spec_path = ROOT / "tools" / "lessons" / (Path(filename).stem.replace("-", "_") + ".json")
    if not spec_path.is_file():
        raise FileNotFoundError(f"Missing video narration source: {spec_path}")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    narrations = [
        scene.get("narration", "").strip()
        for scene in spec.get("scenes", [])
        if scene.get("narration", "").strip()
    ]
    if not narrations:
        raise ValueError(f"No narration text found in {spec_path}")
    return narrations


def metadata_block(path, base_url, title, heading, description):
    relative_path = path.relative_to(ROOT)
    canonical = page_url(base_url, relative_path)
    name = heading or title or "知多丸式 学習ポータル"
    breadcrumbs = lesson_breadcrumbs(relative_path, base_url, heading or title)
    breadcrumb_schema = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": item["name"],
                "item": item["url"],
            }
            for position, item in enumerate(breadcrumbs, start=1)
        ],
    }
    page_schema = {
        "@type": "WebPage",
        "name": name,
        "description": description,
        "url": canonical,
        "inLanguage": "ja",
        "isPartOf": {
            "@type": "WebSite",
            "@id": base_url,
            "name": "知多丸式 学習ポータル",
            "url": base_url,
        },
    }
    graph = [page_schema, breadcrumb_schema]
    if relative_path.parts[:1] == ("subjects",) and "lessons" in relative_path.parts:
        graph.append(
            {
                "@type": "LearningResource",
                "name": name,
                "description": description,
                "learningResourceType": "解説レッスン",
                "inLanguage": "ja",
                "isAccessibleForFree": True,
                "url": canonical,
                "isPartOf": {"@id": base_url},
            }
        )
    if relative_path == Path("index.html"):
        graph.extend(
            [
                {
                    "@type": "WebSite",
                    "@id": base_url,
                    "name": "知多丸式 学習ポータル",
                    "url": base_url,
                    "inLanguage": "ja",
                },
                {
                    "@type": "Organization",
                    "@id": base_url + "#organization",
                    "name": "知多丸式 学習ポータル",
                    "url": base_url,
                },
            ]
        )

    items = [
        f'<link rel="canonical" href="{html.escape(canonical, quote=True)}">',
        f'<meta property="og:title" content="{html.escape(title or name, quote=True)}">',
        f'<meta property="og:description" content="{html.escape(description, quote=True)}">',
        f'<meta property="og:url" content="{html.escape(canonical, quote=True)}">',
        '<meta property="og:type" content="article">'
        if "lessons" in relative_path.parts
        else '<meta property="og:type" content="website">',
        '<meta property="og:locale" content="ja_JP">',
        '<meta name="twitter:card" content="summary">',
        (
            '<script type="application/ld+json">'
            + json.dumps(
                {"@context": "https://schema.org", "@graph": graph},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "</script>"
        ),
    ]
    return SEO_MARKER + "\n" + "\n".join(items) + "\n" + SEO_END_MARKER


def update_html(path, base_url):
    source = path.read_text(encoding="utf-8")
    source = re.sub(
        re.escape(SEO_MARKER) + r".*?" + re.escape(SEO_END_MARKER) + r"\s*",
        "",
        source,
        flags=re.S,
    )
    source = re.sub(
        r'<section class="video-transcript".*?</section>\s*',
        "",
        source,
        flags=re.S,
    )
    title, heading, description, video_src = parse_page(source)
    if not title or not description:
        raise ValueError(f"Missing title or description: {path.relative_to(ROOT)}")
    metadata = metadata_block(
        path, base_url, title, heading, description
    )
    if not re.search(r"</head\s*>", source, re.I):
        raise ValueError(f"Missing </head> in {path.relative_to(ROOT)}")
    source = re.sub(
        r"</head\s*>",
        metadata + "\n</head>",
        source,
        count=1,
        flags=re.I,
    )

    narrations = video_narrations(video_src)
    if narrations:
        transcript = (
            '\n<section class="video-transcript" aria-labelledby="video-transcript-heading">\n'
            "<h2 id=\"video-transcript-heading\">動画の音声ナレーション</h2>\n"
            "<details>\n<summary>解説の全文を読む</summary>\n"
            "<ol>\n"
            + "".join(
                f"<li>{html.escape(narration)}</li>\n"
                for narration in narrations
            )
            + "</ol>\n</details>\n</section>\n"
        )
        if re.search(r"</main\s*>", source, re.I):
            source = re.sub(
                r"</main\s*>",
                transcript + "</main>",
                source,
                count=1,
                flags=re.I,
            )
        elif re.search(r"</body\s*>", source, re.I):
            source = re.sub(
                r"</body\s*>",
                transcript + "</body>",
                source,
                count=1,
                flags=re.I,
            )
        else:
            raise ValueError(f"Missing </main> and </body> in {path.relative_to(ROOT)}")
    path.write_text(source, encoding="utf-8", newline="\n")
    return bool(narrations)


def build_sitemap(paths, base_url):
    ET.register_namespace("", SITEMAP_NS)
    urlset = ET.Element(f"{{{SITEMAP_NS}}}urlset")
    for path in paths:
        relative = path.relative_to(ROOT)
        canonical = page_url(base_url, relative)
        url = ET.SubElement(urlset, f"{{{SITEMAP_NS}}}url")
        ET.SubElement(url, f"{{{SITEMAP_NS}}}loc").text = canonical
    ET.ElementTree(urlset).write(
        ROOT / "sitemap.xml",
        encoding="utf-8",
        xml_declaration=True,
    )


def validate_base_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise argparse.ArgumentTypeError("The base URL must be an absolute HTTPS URL.")
    if parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError("The base URL cannot include a query or fragment.")
    return value.rstrip("/") + "/"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", type=validate_base_url, default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    pages = sorted(
        path
        for path in ROOT.rglob("*.html")
        if ".git" not in path.relative_to(ROOT).parts
    )
    transcript_count = sum(update_html(path, args.base_url) for path in pages)
    build_sitemap(pages, args.base_url)
    print(
        f"Updated {len(pages)} HTML pages, added {transcript_count} video transcripts, "
        f"and generated sitemap.xml for {args.base_url}"
    )


if __name__ == "__main__":
    main()
