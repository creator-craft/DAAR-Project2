import re
import time
from collections import Counter
from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import NotRequired, TypedDict

import re2
from django.db.models import Count, Max, Sum
from rest_framework.exceptions import ValidationError

from library.constants import (
    MATCHED_TERMS_LIMIT,
    MAX_REGEX_TERMS,
    MIN_BOOKS,
    MIN_WORDS_PER_BOOK,
    PAGE_SIZE,
    RECOMMENDATION_LIMIT,
    RECOMMENDATION_SEEDS,
    TERM_QUERY_CHUNK,
)
from library.models import Book, Posting, Similarity, Term

ALLOWED_PATTERN = re.compile(r"[\w.|()*+?\[\]^-]+")
VOCABULARY_CHUNK = 50_000


class SearchMode(StrEnum):
    KEYWORD = "keyword"
    REGEX = "regex"


class Ranking(StrEnum):
    PAGERANK = "pagerank"
    FREQUENCY = "frequency"


class LibraryStats(TypedDict):
    books: int
    words: int
    terms: int
    graph: bool
    corpus_ready: bool


class BookResult(TypedDict):
    id: int
    title: str
    author: str
    occurrences: int
    pagerank: float


class Recommendation(TypedDict):
    id: int
    title: str
    author: str
    similarity: float


class SearchResponse(TypedDict):
    query: str
    mode: str
    total: int
    elapsed_ms: int
    page_size: int
    graph_ready: bool
    results: list[BookResult]
    recommendations: list[Recommendation]
    matched_term_count: NotRequired[int]
    matched_terms: NotRequired[list[str]]


def library_stats() -> LibraryStats:
    totals = Book.objects.aggregate(books=Count("id"), words=Sum("word_count"))
    books: int = totals["books"]
    return {
        "books": books,
        "words": totals["words"] or 0,
        "terms": Term.objects.count(),
        "graph": Similarity.objects.exists(),
        "corpus_ready": books >= MIN_BOOKS
        and not Book.objects.filter(word_count__lt=MIN_WORDS_PER_BOOK).exists(),
    }


def compile_pattern(pattern: str) -> Callable[[str], object]:
    """Compile a case-insensitive whole-word matcher. RE2 guarantees linear-time matching"""
    if not ALLOWED_PATTERN.fullmatch(pattern):
        raise ValidationError("Unsupported character in regular expression.")
    try:
        matcher: Callable[[str], object] = re2.compile(f"(?i:{pattern})").fullmatch
    except re2.error:
        raise ValidationError("Invalid regular expression.") from None
    return matcher


def matching_terms(query: str, mode: SearchMode) -> list[tuple[int, str]]:
    if mode is SearchMode.KEYWORD:
        return list(Term.objects.filter(word=query.lower()).values_list("id", "word"))
    matches = compile_pattern(query)
    vocabulary = Term.objects.values_list("id", "word").iterator(
        chunk_size=VOCABULARY_CHUNK
    )
    return sorted(
        (term for term in vocabulary if matches(term[1])), key=lambda term: term[1]
    )


def occurrences_by_book(term_ids: Sequence[int]) -> Counter[int]:
    totals: Counter[int] = Counter()
    for start in range(0, len(term_ids), TERM_QUERY_CHUNK):
        rows = (
            Posting.objects.filter(
                term_id__in=term_ids[start : start + TERM_QUERY_CHUNK]
            )
            .values("book_id")
            .annotate(total=Sum("occurrences"))
        )
        for row in rows:
            totals[row["book_id"]] += row["total"]
    return totals


def rank_books(occurrences: Counter[int], ranking: Ranking) -> list[int]:
    if ranking is Ranking.FREQUENCY:
        return sorted(occurrences, key=lambda book_id: (-occurrences[book_id], book_id))
    pageranks: dict[int, float] = dict(Book.objects.values_list("id", "pagerank"))
    return sorted(
        occurrences,
        key=lambda book_id: (-pageranks[book_id], -occurrences[book_id], book_id),
    )


def recommend(seed_ids: Sequence[int]) -> list[Recommendation]:
    """Books closest in the Jaccard graph to the best results, excluding those results"""
    rows = list(
        Similarity.objects.filter(source_id__in=seed_ids)
        .exclude(target_id__in=seed_ids)
        .values("target_id")
        .annotate(best=Max("similarity"))
        .order_by("-best", "target_id")[:RECOMMENDATION_LIMIT]
    )
    books = Book.objects.in_bulk([row["target_id"] for row in rows])
    return [
        {
            "id": row["target_id"],
            "title": books[row["target_id"]].title,
            "author": books[row["target_id"]].author,
            "similarity": row["best"],
        }
        for row in rows
    ]


def run_search(
    query: str, mode: SearchMode, ranking: Ranking, page: int
) -> SearchResponse:
    started = time.perf_counter()
    terms = matching_terms(query, mode)
    if len(terms) > MAX_REGEX_TERMS:
        raise ValidationError(
            f"Expression too broad: {len(terms)} indexed words match. Please refine it."
        )
    occurrences = occurrences_by_book([term_id for term_id, _ in terms])
    ranked = rank_books(occurrences, ranking)

    if page > max(1, -(-len(ranked) // PAGE_SIZE)):
        raise ValidationError("Page out of range.")
    page_ids = ranked[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
    books = Book.objects.in_bulk(page_ids)

    results: list[BookResult] = [
        {
            "id": book_id,
            "title": books[book_id].title,
            "author": books[book_id].author,
            "occurrences": occurrences[book_id],
            "pagerank": books[book_id].pagerank,
        }
        for book_id in page_ids
    ]
    recommendations = recommend(ranked[:RECOMMENDATION_SEEDS])
    graph_ready = Similarity.objects.exists()

    response: SearchResponse = {
        "query": query,
        "mode": mode.value,
        "total": len(ranked),
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "page_size": PAGE_SIZE,
        "graph_ready": graph_ready,
        "results": results,
        "recommendations": recommendations,
    }
    if mode is SearchMode.REGEX:
        response["matched_term_count"] = len(terms)
        response["matched_terms"] = [word for _, word in terms[:MATCHED_TERMS_LIMIT]]
    return response
