#!/usr/bin/env python3
"""Fetch every source in a distillation profile, clean it to text, and split it into chunks.

Sources that already have chunks are skipped, so the command is safe to re-run
after adding sources or after a transient failure.
"""
import argparse
import gzip
import hashlib
import html.parser
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
MIN_CHUNK_CHARS = 6000
MAX_CHUNK_CHARS = 10000
MIN_DOCUMENT_CHARS = 500
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
BLOCKED_STATUSES = {401, 403, 407, 429, 451}
DROPPED_TAGS = {
    "script", "style", "nav", "header", "footer", "aside",
    "noscript", "svg", "template", "iframe",
}
HEADING_TAGS = {"h1", "h2", "h3", "h4"}
BLOCK_TAGS = {
    "p", "div", "li", "br", "tr", "section", "article", "blockquote",
    "pre", "table", "ul", "ol", "dt", "dd", "h5", "h6",
}


class SourceFailure(Exception):
    pass


class TextExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.dropped_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROPPED_TAGS:
            self.dropped_depth += 1
        elif self.dropped_depth:
            return
        elif tag in HEADING_TAGS:
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in DROPPED_TAGS:
            self.dropped_depth = max(0, self.dropped_depth - 1)
        elif not self.dropped_depth and tag in HEADING_TAGS | BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_data(self, data):
        if not self.dropped_depth:
            self.parts.append(data)


def is_url(source):
    return source.startswith(("http://", "https://"))


def slug_for(source):
    readable = re.sub(r"^https?://(www\.)?", "", source)
    readable = re.sub(r"[^a-z0-9]+", "-", readable.lower()).strip("-")[-60:].strip("-")
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:6]
    return f"{readable}-{digest}"


def download(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain,*/*"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read(MAX_DOWNLOAD_BYTES)
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        content_type = response.headers.get_content_type()
        charset = response.headers.get_content_charset() or "utf-8"
    if not content_type.startswith("text/") and "html" not in content_type:
        raise SourceFailure(f"unsupported content type {content_type}")
    return body.decode(charset, errors="replace")


def read_source(source):
    if not is_url(source):
        try:
            with open(source, encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError as error:
            raise SourceFailure(f"unreadable file: {error.strerror}")
    for attempt in (1, 2):
        try:
            return download(source)
        except urllib.error.HTTPError as error:
            if error.code in BLOCKED_STATUSES:
                raise SourceFailure(f"blocked: HTTP {error.code}")
            failure = f"error: HTTP {error.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            failure = f"error: {getattr(error, 'reason', error)}"
        if attempt == 1:
            time.sleep(5)
    raise SourceFailure(failure)


def to_paragraphs(text):
    if re.search(r"<(html|body|div|p|article)\b", text, re.IGNORECASE):
        extractor = TextExtractor()
        extractor.feed(text)
        text = "".join(extractor.parts)
        blocks = (re.sub(r"\s+", " ", block).strip() for block in re.split(r"\n\s*\n", text))
    else:
        blocks = (block.strip() for block in re.split(r"\n\s*\n", text))
    return [block for block in blocks if block]


def split_oversized(paragraphs):
    for paragraph in paragraphs:
        for start in range(0, len(paragraph), MAX_CHUNK_CHARS):
            yield paragraph[start:start + MAX_CHUNK_CHARS]


def pack_chunks(paragraphs):
    chunks, current, size = [], [], 0
    for paragraph in split_oversized(paragraphs):
        starts_section = paragraph.startswith("#")
        overflows = size + len(paragraph) > MAX_CHUNK_CHARS
        if current and (overflows or (starts_section and size >= MIN_CHUNK_CHARS)):
            chunks.append("\n\n".join(current))
            current, size = [], 0
        current.append(paragraph)
        size += len(paragraph) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_source(source, slug, chunks_dir):
    paragraphs = to_paragraphs(read_source(source))
    total_chars = sum(len(paragraph) for paragraph in paragraphs)
    if total_chars < MIN_DOCUMENT_CHARS:
        raise SourceFailure("empty: under 500 characters of text, likely blocked or script-rendered")
    chunks = pack_chunks(paragraphs)
    for index, chunk in enumerate(chunks, start=1):
        path = os.path.join(chunks_dir, f"{slug}__{index:03d}.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"SOURCE: {source}\n\n{chunk}\n")
    return len(chunks), total_chars


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", help="path to profile.json; staging is created beside it")
    args = parser.parse_args()

    with open(args.profile, encoding="utf-8") as handle:
        profile = json.load(handle)
    staging = os.path.join(os.path.dirname(os.path.abspath(args.profile)), ".staging")
    chunks_dir = os.path.join(staging, "chunks")
    fragments_dir = os.path.join(staging, "fragments")
    os.makedirs(chunks_dir, exist_ok=True)
    os.makedirs(fragments_dir, exist_ok=True)

    failed = []
    for source in profile["sources"]:
        slug = slug_for(source)
        if any(name.startswith(f"{slug}__") for name in os.listdir(chunks_dir)):
            print(f"kept\t{source}")
            continue
        try:
            count, chars = chunk_source(source, slug, chunks_dir)
            print(f"chunked\t{source}\tchunks={count}\tchars={chars}")
        except SourceFailure as failure:
            failed.append(source)
            print(f"FAILED\t{source}\t{failure}")

    to_map = sorted(
        os.path.join(chunks_dir, name)
        for name in os.listdir(chunks_dir)
        if not os.path.exists(os.path.join(fragments_dir, name))
    )
    to_map_path = os.path.join(staging, "to-map.txt")
    with open(to_map_path, "w", encoding="utf-8") as handle:
        handle.write("".join(f"{path}\n" for path in to_map))
    print(f"chunks={len(os.listdir(chunks_dir))}\tto_map={len(to_map)}\tfailed={len(failed)}")
    print(f"to-map list: {to_map_path}")
    print(f"fragments dir: {fragments_dir}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
