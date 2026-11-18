"""Relevance test of the rankings and recommendations against the Project Gutenberg catalog.

A book is relevant to a query when one of its catalog labels (Subjects or Bookshelves, assigned
by librarians, independently of this search engine) contains the query word. Every query is run
on the indexed library; the precision of the first results of each ranking is compared with the
precision of a random order of the same results.
"""

import csv
import gzip
import io
import re
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from library.constants import RECOMMENDATION_SEEDS
from library.download import CATALOG_FILE
from library.models import Book
from library.search import (
    Ranking,
    SearchMode,
    matching_terms,
    occurrences_by_book,
    rank_books,
    recommend,
)

# 5 topics labelled on at least 50 books, 10 topics labelled on 10 to 30 books
QUERIES: list[tuple[str, str]] = [
    ("popular", "adventure"),
    ("popular", "science"),
    ("popular", "philosophy"),
    ("popular", "love"),
    ("popular", "detective"),
    ("niche", "rome"),
    ("niche", "fairy"),
    ("niche", "scotland"),
    ("niche", "horror"),
    ("niche", "magic"),
    ("niche", "engineering"),
    ("niche", "knights"),
    ("niche", "christmas"),
    ("niche", "revolution"),
    ("niche", "india"),
]

# Case studies, inspected book by book. A label word must equal a term, or start with a term
# ending with "*". "sargon" is no label word, so its books are those about Babylonia or Assyria.
CASES: list[tuple[str, tuple[str, ...]]] = [
    ("holmes", ("holmes",)),
    ("detective", ("detective",)),
    ("love", ("love",)),
    ("chemistry", ("chemistry",)),
    ("sargon", ("babylon*", "assyri*")),
]

LABEL_WORD = re.compile(r"[a-z]+")

RESULT_FIELDS = ["query", "group", "ranking", "rank", "book_id", "title", "relevant"]
CASE_FIELDS = ["query", "ranking", "rank", "book_id", "title", "occurrences", "relevant"]
CASE_RECOMMENDATION_FIELDS = ["query", "ranking", "rank", "book_id", "title", "similarity", "relevant"]
SUMMARY_FIELDS = [
    "query",
    "group",
    "labelled",
    "matched",
    "relevant_matched",
    "baseline",
    "precision_frequency",
    "precision_pagerank",
    "recommendations_frequency",
    "recommendations_pagerank",
    "recommendations_baseline",
]


def catalog_labels(path: Path, books: set[int]) -> dict[int, set[str]]:
    """Lowercase words of the Subjects and Bookshelves of every indexed book"""
    rows = csv.DictReader(io.StringIO(gzip.decompress(path.read_bytes()).decode("utf-8")))
    labels: dict[int, set[str]] = {}
    for row in rows:
        if row["Text#"].isdecimal() and int(row["Text#"]) in books:
            text = f"{row['Subjects']} {row['Bookshelves']}".lower()
            labels[int(row["Text#"])] = set(LABEL_WORD.findall(text))
    return labels


def labelled_with(labels: dict[int, set[str]], terms: tuple[str, ...]) -> set[int]:
    def matches(word: str) -> bool:
        return any(
            word.startswith(term[:-1]) if term.endswith("*") else word == term for term in terms
        )

    return {book for book, words in labels.items() if any(map(matches, words))}


def precision(book_ids: list[int], relevant: set[int]) -> float:
    return sum(book in relevant for book in book_ids) / len(book_ids) if book_ids else 0.0


class Command(BaseCommand):
    help = "Measure the precision of the rankings and recommendations against catalog labels."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--top", type=int, default=10, help="Results evaluated per query")
        parser.add_argument(
            "--output",
            type=Path,
            default=settings.DATA_DIR / "relevance",
            help="Directory of results.csv and summary.csv",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        catalog = settings.CORPUS_DIR / CATALOG_FILE
        if not catalog.exists():
            raise CommandError(f"No catalog found at {catalog}: run download_corpus first.")
        top: int = options["top"]
        titles = dict(Book.objects.values_list("id", "title"))
        labels = catalog_labels(catalog, set(titles))

        output: Path = options["output"]
        output.mkdir(parents=True, exist_ok=True)
        with (
            open(output / "results.csv", "w", newline="") as results_file,
            open(output / "summary.csv", "w", newline="") as summary_file,
            open(output / "cases.csv", "w", newline="") as cases_file,
            open(output / "case_recommendations.csv", "w", newline="") as suggestions_file,
        ):
            results = csv.DictWriter(results_file, RESULT_FIELDS)
            summary = csv.DictWriter(summary_file, SUMMARY_FIELDS)
            results.writeheader()
            summary.writeheader()

            for group, query in QUERIES:
                relevant = {book for book, words in labels.items() if query in words}
                occurrences = occurrences_by_book(
                    [term_id for term_id, _ in matching_terms(query, SearchMode.KEYWORD)]
                )
                row: dict[str, Any] = {
                    "query": query,
                    "group": group,
                    "labelled": len(relevant),
                    "matched": len(occurrences),
                    "relevant_matched": len(relevant & set(occurrences)),
                    "baseline": round(precision(list(occurrences), relevant), 4),
                    "recommendations_baseline": round(len(relevant) / len(titles), 4),
                }
                for ranking in Ranking:
                    ranked = rank_books(occurrences, ranking)[:top]
                    for rank, book in enumerate(ranked, start=1):
                        results.writerow(
                            {
                                "query": query,
                                "group": group,
                                "ranking": ranking.value,
                                "rank": rank,
                                "book_id": book,
                                "title": titles[book],
                                "relevant": int(book in relevant),
                            }
                        )
                    suggested = [book["id"] for book in recommend(ranked[:RECOMMENDATION_SEEDS])]
                    row[f"precision_{ranking.value}"] = round(precision(ranked, relevant), 4)
                    row[f"recommendations_{ranking.value}"] = round(
                        precision(suggested, relevant), 4
                    )
                summary.writerow(row)
                print(
                    f"{query:12} P@{top} occurrences {row['precision_frequency']:.2f}, "
                    f"PageRank {row['precision_pagerank']:.2f}, random {row['baseline']:.2f}"
                )

            cases = csv.DictWriter(cases_file, CASE_FIELDS)
            suggestions = csv.DictWriter(suggestions_file, CASE_RECOMMENDATION_FIELDS)
            cases.writeheader()
            suggestions.writeheader()
            for query, terms in CASES:
                relevant = labelled_with(labels, terms)
                occurrences = occurrences_by_book(
                    [term_id for term_id, _ in matching_terms(query, SearchMode.KEYWORD)]
                )
                for ranking in Ranking:
                    ranked = rank_books(occurrences, ranking)[:top]
                    for rank, book in enumerate(ranked, start=1):
                        cases.writerow(
                            {
                                "query": query,
                                "ranking": ranking.value,
                                "rank": rank,
                                "book_id": book,
                                "title": titles[book],
                                "occurrences": occurrences[book],
                                "relevant": int(book in relevant),
                            }
                        )
                    for rank, book in enumerate(recommend(ranked[:RECOMMENDATION_SEEDS]), start=1):
                        suggestions.writerow(
                            {
                                "query": query,
                                "ranking": ranking.value,
                                "rank": rank,
                                "book_id": book["id"],
                                "title": book["title"],
                                "similarity": round(book["similarity"], 4),
                                "relevant": int(book["id"] in relevant),
                            }
                        )
                    found = [rank for rank, book in enumerate(ranked, 1) if book in relevant]
                    print(f"case {query:10} {ranking.value:9} relevant at ranks {found}")
        print(self.style.SUCCESS(f"Results written to {output}"))
