"""Performance benchmark of the search engine on increasingly large samples of the corpus.

For every sample size, the books are indexed from scratch into a scratch SQLite database
(the library served by the API is never touched), the time spent in each indexing phase is
recorded, then a fixed set of queries is replayed to measure the search latency.
Samples are nested (the 200-book sample contains the 100-book one) and drawn with a fixed seed,
so that two runs on the same corpus measure the same books.
"""

import csv
import random
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from library import indexing
from library.constants import MIN_WORDS_PER_BOOK
from library.corpus import corpus_files
from library.models import Book
from library.search import Ranking, SearchMode, run_search

DEFAULT_SIZES = "100,200,400,800,1200,all"
DEFAULT_SEED = 2026

QUERIES: list[tuple[SearchMode, str]] = [
    (SearchMode.KEYWORD, "the"),
    (SearchMode.KEYWORD, "telescope"),
    (SearchMode.KEYWORD, "sargon"),
    (SearchMode.REGEX, "sarg.n"),
    (SearchMode.REGEX, "theat(re|er)"),
    (SearchMode.REGEX, "telescop(e|es|ic)"),
    (SearchMode.REGEX, "[a-z]+ism"),
]

# Functions called by `rebuild_index`, timed separately. The rest of the build
# (vocabulary, incidence matrix, bulk inserts of terms, books and edges) is reported as "other".
PHASES = {
    "read_book": "parse_s",
    "insert_postings": "postings_s",
    "jaccard_similarity": "jaccard_s",
    "nearest_edges": "neighbours_s",
    "pagerank": "pagerank_s",
}

INDEXING_FIELDS = [
    "books",
    "words",
    "terms",
    "postings",
    "edges",
    "db_mb",
    *PHASES.values(),
    "other_s",
    "total_s",
]
QUERY_FIELDS = [
    "books",
    "mode",
    "ranking",
    "query",
    "run",
    "ms",
    "matched_terms",
    "results",
]


def timer(
    function: Callable[..., Any], phase: str, timings: dict[str, float]
) -> Callable[..., Any]:
    def timed(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            timings[phase] += time.perf_counter() - started

    return timed


@contextmanager
def timed_phases(timings: dict[str, float]) -> Iterator[None]:
    with ExitStack() as stack:
        for name, phase in PHASES.items():
            original = getattr(indexing, name)
            stack.enter_context(
                patch.object(indexing, name, timer(original, phase, timings))
            )
        yield


def use_scratch_database(path: Path) -> None:
    connection.close()
    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)
    # Same mechanism as Django's test runner: later queries open the new file
    connection.settings_dict["NAME"] = path
    call_command("migrate", verbosity=0)


def database_megabytes() -> float:
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA page_count")
        pages = cursor.fetchone()[0]
        cursor.execute("PRAGMA page_size")
        page_size = cursor.fetchone()[0]
    return round(pages * page_size / 1e6, 1)


def parse_sizes(value: str, available: int) -> list[int]:
    sizes: set[int] = set()
    for token in value.split(","):
        token = token.strip()
        if token == "all":
            sizes.add(available)
        elif token.isdecimal() and int(token) > 0:
            sizes.add(min(int(token), available))
        else:
            raise CommandError(f"Invalid sample size: {token!r}")
    return sorted(sizes)


class Command(BaseCommand):
    help = "Measure index build time and search latency on nested samples of the corpus."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--sizes",
            default=DEFAULT_SIZES,
            help=f"Comma-separated sample sizes, 'all' for the whole corpus (default: {DEFAULT_SIZES})",
        )
        parser.add_argument("--repeat", type=int, default=5, help="Timed runs per query")
        parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
        parser.add_argument(
            "--output",
            type=Path,
            default=settings.DATA_DIR / "benchmark",
            help="Directory of indexing.csv and queries.csv",
        )
        parser.add_argument(
            "--database",
            type=Path,
            default=Path("/tmp/benchmark.sqlite3"),
            help="Scratch SQLite file, erased before every sample",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        files = corpus_files(settings.CORPUS_DIR)
        if not files:
            raise CommandError(f"No <id>.txt book found in {settings.CORPUS_DIR}.")
        if options["repeat"] < 1:
            raise CommandError("--repeat must be positive.")
        sizes = parse_sizes(options["sizes"], len(files))
        if options["database"].resolve() == Path(connection.settings_dict["NAME"]).resolve():
            raise CommandError("The benchmark database must not be the library database.")
        random.Random(options["seed"]).shuffle(files)

        output: Path = options["output"]
        output.mkdir(parents=True, exist_ok=True)
        with (
            open(output / "indexing.csv", "w", newline="") as indexing_file,
            open(output / "queries.csv", "w", newline="") as queries_file,
        ):
            indexing_csv = csv.DictWriter(indexing_file, INDEXING_FIELDS)
            queries_csv = csv.DictWriter(queries_file, QUERY_FIELDS)
            indexing_csv.writeheader()
            queries_csv.writeheader()

            for size in sizes:
                use_scratch_database(options["database"])
                row = self.measure_indexing(sorted(files[:size]))
                indexing_csv.writerow(row)
                indexing_file.flush()
                print(
                    f"{row['books']} books: indexed in {row['total_s']:.1f} s "
                    f"({row['terms']} terms, {row['postings']} postings, {row['db_mb']} MB)"
                )
                for query_row in self.measure_queries(row["books"], options["repeat"]):
                    queries_csv.writerow(query_row)
                queries_file.flush()

        connection.close()
        for suffix in ("", "-wal", "-shm"):
            Path(f"{options['database']}{suffix}").unlink(missing_ok=True)
        print(self.style.SUCCESS(f"Results written to {output}"))

    def measure_indexing(self, files: list[tuple[int, Path]]) -> dict[str, Any]:
        timings: dict[str, float] = defaultdict(float)
        started = time.perf_counter()
        with timed_phases(timings):
            summary = indexing.rebuild_index(files, MIN_WORDS_PER_BOOK, lambda _: None)
        total = time.perf_counter() - started
        return {
            "books": summary.books,
            "words": Book.objects.aggregate(words=Sum("word_count"))["words"] or 0,
            "terms": summary.terms,
            "postings": summary.postings,
            "edges": summary.edges,
            "db_mb": database_megabytes(),
            **{phase: round(timings[phase], 6) for phase in PHASES.values()},
            "other_s": round(total - sum(timings.values()), 6),
            "total_s": round(total, 6),
        }

    def measure_queries(self, books: int, repeat: int) -> Iterator[dict[str, Any]]:
        for mode, query in QUERIES:
            for ranking in Ranking:
                try:
                    run_search(query, mode, ranking, 1)  # warm-up, not recorded
                except ValidationError as error:
                    print(self.style.WARNING(f"  {query!r} skipped: {error.detail}"))
                    break
                for run in range(1, repeat + 1):
                    started = time.perf_counter()
                    response = run_search(query, mode, ranking, 1)
                    elapsed = (time.perf_counter() - started) * 1000
                    yield {
                        "books": books,
                        "mode": mode.value,
                        "ranking": ranking.value,
                        "query": query,
                        "run": run,
                        "ms": round(elapsed, 2),
                        "matched_terms": response.get(
                            "matched_term_count", int(response["total"] > 0)
                        ),
                        "results": response["total"],
                    }
