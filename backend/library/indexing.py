from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import numpy as np
from django.db import connection, transaction
from numpy.typing import NDArray
from scipy.sparse import csr_matrix

from library.constants import NEIGHBOURS_PER_BOOK
from library.corpus import read_book
from library.graph import jaccard_similarity, nearest_edges, pagerank
from library.models import Book, Posting, Similarity, Term


class BookInfo(NamedTuple):
    id: int
    title: str
    author: str
    word_count: int


@dataclass(frozen=True, slots=True)
class IndexSummary:
    books: int
    skipped: int
    terms: int
    postings: int
    edges: int


def insert_postings(book_id: int, indices: list[int], occurrences: list[int]) -> None:
    """Raw bulk insert is roughly 5x faster than `bulk_create` for millions of rows"""
    with connection.cursor() as cursor:
        cursor.executemany(
            f"INSERT INTO {Posting._meta.db_table} (book_id, term_id, occurrences) VALUES (%s, %s, %s)",
            [(book_id, index + 1, count) for index, count in zip(indices, occurrences)],
        )


def clear_index() -> None:
    with connection.cursor() as cursor:
        for model in (Similarity, Posting, Term, Book):
            cursor.execute(f"DELETE FROM {model._meta.db_table}")


@transaction.atomic
def rebuild_index(
    files: list[tuple[int, Path]], min_words: int, report: Callable[[str], None]
) -> IndexSummary:
    """Rebuild the inverted index, the Jaccard graph and the PageRank of every book, atomically"""
    clear_index()
    vocabulary: dict[str, int] = {}
    infos: list[BookInfo] = []
    term_indices: list[NDArray[np.int32]] = []
    skipped = postings = 0

    for number, (identifier, path) in enumerate(files, start=1):
        parsed = read_book(path)
        if parsed.word_count < min_words:
            skipped += 1
            report(f"Book #{identifier} has too few words")
            continue
        indices = [
            vocabulary.setdefault(word, len(vocabulary)) for word in parsed.frequencies
        ]
        insert_postings(identifier, indices, list(parsed.frequencies.values()))
        infos.append(
            BookInfo(
                identifier, parsed.title[:512], parsed.author[:256], parsed.word_count
            )
        )
        term_indices.append(np.array(indices, dtype=np.int32))
        postings += len(indices)
        report(f"#{identifier}: Indexed {number}/{len(files)} books")

    Term.objects.bulk_create(
        Term(id=index + 1, word=word) for word, index in vocabulary.items()
    )

    indptr = np.cumsum([0, *map(len, term_indices)])
    incidence = csr_matrix(
        (np.ones(postings, dtype=np.int32), np.concatenate(term_indices), indptr),
        shape=(len(infos), len(vocabulary)),
    )
    edges = nearest_edges(jaccard_similarity(incidence), NEIGHBOURS_PER_BOOK)
    ranks = pagerank(len(infos), edges)

    Book.objects.bulk_create(
        Book(
            id=info.id,
            title=info.title,
            author=info.author,
            word_count=info.word_count,
            pagerank=float(rank),
        )
        for info, rank in zip(infos, ranks)
    )
    Similarity.objects.bulk_create(
        Similarity(
            source_id=infos[edge.source].id,
            target_id=infos[edge.target].id,
            similarity=edge.similarity,
        )
        for edge in edges
    )
    return IndexSummary(len(infos), skipped, len(vocabulary), postings, len(edges))
