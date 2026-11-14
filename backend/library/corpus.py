import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from library.constants import MAX_WORD_LENGTH, MIN_WORD_LENGTH

WORD = re.compile(r"[^\W\d_]+")
START_MARKER = re.compile(r"\*\*\* ?START OF .*?\*\*\*", re.IGNORECASE)
END_MARKER = re.compile(r"\*\*\* ?END OF ", re.IGNORECASE)
HEADER_SIZE = 5_000


@dataclass(frozen=True, slots=True)
class ParsedBook:
    title: str
    author: str
    language: str
    frequencies: Counter[str]

    @property
    def word_count(self) -> int:
        return sum(self.frequencies.values())


def header_field(header: str, name: str) -> str:
    match = re.search(rf"^{name}:[ \t]*(.+?)[ \t]*$", header, re.MULTILINE)
    return match.group(1) if match else ""


def parse_book(text: str) -> ParsedBook:
    start = START_MARKER.search(text)
    body_start = start.end() if start else 0
    end = END_MARKER.search(text, body_start)
    header = text[: start.start()] if start else text[:HEADER_SIZE]
    body = text[body_start : end.start() if end else len(text)]
    words = (
        word
        for word in WORD.findall(body.lower())
        if MIN_WORD_LENGTH <= len(word) <= MAX_WORD_LENGTH
    )
    return ParsedBook(
        title=header_field(header, "Title") or "Untitled",
        author=header_field(header, "Author") or "Unknown",
        language=header_field(header, "Language"),
        frequencies=Counter(words),
    )


def read_book(path: Path) -> ParsedBook:
    return parse_book(path.read_text(encoding="utf-8", errors="replace"))


def corpus_files(directory: Path) -> list[tuple[int, Path]]:
    """Return `(gutenberg_id, path)` for every `<id>.txt` file of the corpus, sorted by id"""
    return sorted(
        (int(path.stem), path)
        for path in directory.glob("*.txt")
        if path.stem.isdecimal()
    )
