from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from library.constants import MIN_BOOKS, MIN_WORDS_PER_BOOK
from library.corpus import corpus_files
from library.indexing import rebuild_index


class Command(BaseCommand):
    help = (
        "Index the corpus, then build the Jaccard graph and the PageRank of every book."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--min-words", type=int, default=MIN_WORDS_PER_BOOK)

    def handle(self, *args: Any, **options: Any) -> None:
        files = corpus_files(settings.CORPUS_DIR)
        if not files:
            raise CommandError(f"No <id>.txt book found in {settings.CORPUS_DIR}.")
        summary = rebuild_index(files, options["min_words"], print)
        print(
            self.style.SUCCESS(
                f"{summary.books} books indexed ({summary.skipped} skipped), {summary.terms} terms, "
                f"{summary.postings} postings, {summary.edges} graph edges."
            )
        )
        if summary.books < MIN_BOOKS:
            print(
                self.style.WARNING(
                    f"The assignment requires at least {MIN_BOOKS} books."
                )
            )
