"""Download the corpus from Project Gutenberg mirrors.

Project Gutenberg forbids automated bulk downloads from www.gutenberg.org and asks
robots to use a mirror instead. The official catalog gives the identifier, title,
author and language of every book. The text comes from a mirror of the main
collection, whose files hold the body of the book without its metadata, so the
metadata of the catalog is written back as a header in front of each saved text.
"""

import csv
import gzip
import io
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import NamedTuple

from library.corpus import START_MARKER, corpus_files, parse_book

DEFAULT_CATALOG = "https://gutenberg.pglaf.org/cache/epub/feeds/pg_catalog.csv.gz"
DEFAULT_MIRROR = (
    "https://www.mirrorservice.org/sites/ftp.ibiblio.org/pub/docs/books/gutenberg"
)
# A book is published as `<id>-0.txt` (UTF-8) or, for older ones, `<id>.txt` (ASCII)
TEXT_SUFFIXES = ("-0", "")
USER_AGENT = "daar-library-corpus/1.0"
CATALOG_FILE = ".catalog.csv.gz"
REJECTED_FILE = ".rejected"
MAX_BOOK_BYTES = 10_000_000
ATTEMPTS = 3
TIMEOUT_SECONDS = 30
DEFAULT_WORKERS = 4

Fetch = Callable[[str], bytes | None]


class CatalogEntry(NamedTuple):
    id: int
    title: str
    author: str
    language: str


@dataclass(frozen=True, slots=True)
class DownloadSummary:
    books: int
    downloaded: int
    rejected: int


def fetch(url: str) -> bytes | None:
    """Return the body of `url`, or `None` when the server does not have it (HTTP 404)"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                body: bytes = response.read()
                return body
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if attempt == ATTEMPTS:
                raise
        except OSError:
            if attempt == ATTEMPTS:
                raise
        time.sleep(5 * attempt)
    return None


def author_name(authors: str) -> str:
    """First author of a catalog entry: `Carroll, Lewis, 1832-1898; ...` gives `Lewis Carroll`"""
    first = re.sub(r"\[.*?\]", "", authors.split(";")[0])
    names = [part.strip() for part in first.split(",")]
    names = [name for name in names if name and not re.search(r"\d", name)]
    return " ".join(reversed(names[:2]))


def read_catalog(catalog: bytes, language: str) -> list[CatalogEntry]:
    """Text books written only in `language`, by increasing identifier, from the gzipped CSV catalog"""
    rows = csv.DictReader(io.StringIO(gzip.decompress(catalog).decode("utf-8")))
    return sorted(
        CatalogEntry(
            int(row["Text#"]),
            " ".join(row["Title"].split()),
            author_name(row["Authors"]),
            row["Language"],
        )
        for row in rows
        if row["Type"] == "Text" and row["Language"] == language
    )


def book_urls(mirror: str, identifier: int) -> list[str]:
    """Candidate addresses of a book: book 1342 is stored in `1/3/4/1342/`, book 7 in `0/7/`"""
    folder = "/".join(str(identifier)[:-1]) or "0"
    urls = [
        f"{mirror}/{folder}/{identifier}/{identifier}{suffix}.txt"
        for suffix in TEXT_SUFFIXES
    ]
    if mirror == "https://gutenberg.pglaf.org":
        urls.insert(0, f"{mirror}/cache/epub/{identifier}/pg{identifier}.txt")
    return urls


def with_header(entry: CatalogEntry, data: bytes) -> str:
    """The text of a book preceded by the header fields that `parse_book` reads"""
    # Mirror files start with a byte order mark and end their lines with CRLF
    text = data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
    start = START_MARKER.search(text)
    # A book without a known author gets no author line, and is indexed as "Unknown"
    author = f"Author: {entry.author}\n\n" if entry.author else ""
    header = f"Title: {entry.title}\n\n{author}Language: {entry.language}\n\n"
    return header + (text[start.start() :] if start else text)


def rejection(text: str, min_words: int) -> str | None:
    """Why a downloaded book cannot join the corpus, or `None` when it can"""
    if not START_MARKER.search(text):
        return "body not delimited"
    words = parse_book(text).word_count
    return f"only {words} words" if words < min_words else None


def read_rejected(path: Path) -> set[int]:
    if not path.exists():
        return set()
    return {int(line) for line in path.read_text().split() if line.isdecimal()}


def cached_catalog(directory: Path, url: str, fetch: Fetch) -> bytes:
    """The catalog is large and its server is slow, so it is downloaded only once"""
    path = directory / CATALOG_FILE
    if path.exists():
        return path.read_bytes()
    catalog = fetch(url)
    if catalog is None:
        raise RuntimeError(f"No catalog found at {url}")
    gzip.decompress(catalog)
    partial = path.with_suffix(".part")
    partial.write_bytes(catalog)
    partial.replace(path)
    return catalog


def download_corpus(
    directory: Path,
    count: int,
    min_words: int,
    report: Callable[[str], None],
    catalog: str = DEFAULT_CATALOG,
    mirror: str = DEFAULT_MIRROR,
    language: str = "en",
    delay: float = 0.2,
    fetch: Fetch = fetch,
    workers: int = DEFAULT_WORKERS,
) -> DownloadSummary:
    """Fill `directory` with `<gutenberg id>.txt` files until it holds `count` books.

    Books are taken by increasing identifier, which makes the corpus reproducible.
    Existing files and previously rejected identifiers are skipped, so an interrupted
    download resumes where it stopped.
    """
    if workers < 1:
        raise ValueError("workers must be positive")
    if delay < 0:
        raise ValueError("delay must be nonnegative")

    directory.mkdir(parents=True, exist_ok=True)
    present = {identifier for identifier, _ in corpus_files(directory)}
    rejected_path = directory / REJECTED_FILE
    rejected = read_rejected(rejected_path)
    downloaded = newly_rejected = 0
    if len(present) >= count:
        return DownloadSummary(len(present), downloaded, newly_rejected)

    report(f"Reading the catalog ({catalog})")
    entries = read_catalog(cached_catalog(directory, catalog, fetch), language)
    mirror = mirror.rstrip("/")

    def download(entry: CatalogEntry) -> tuple[str, str | None]:
        for url in book_urls(mirror, entry.id):
            data = fetch(url)
            time.sleep(delay)
            if data is None:
                continue
            if len(data) > MAX_BOOK_BYTES:
                return "", "file too large"
            text = with_header(entry, data)
            return text, rejection(text, min_words)
        return "", "no plain text file"

    report(f"{len(entries)} candidates in catalog; downloading with {workers} workers")
    candidates = (entry for entry in entries if entry.id not in present and entry.id not in rejected)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while batch := list(islice(candidates, workers)):
            for entry, (text, reason) in zip(batch, pool.map(download, batch)):
                if reason is not None:
                    with rejected_path.open("a", encoding="utf-8") as file:
                        file.write(f"{entry.id}\n")
                    newly_rejected += 1
                    report(f"#{entry.id}: skipped ({reason})")
                    continue
                partial = directory / f"{entry.id}.part"
                partial.write_text(text, encoding="utf-8")
                partial.replace(directory / f"{entry.id}.txt")
                present.add(entry.id)
                downloaded += 1
                report(f"#{entry.id}: downloaded, {len(present)}/{count} books")
                if len(present) >= count:
                    return DownloadSummary(len(present), downloaded, newly_rejected)
    return DownloadSummary(len(present), downloaded, newly_rejected)
