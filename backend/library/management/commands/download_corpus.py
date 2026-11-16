import os
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from library.constants import CORPUS_SIZE, MIN_BOOKS, MIN_WORDS_PER_BOOK
from library.download import DEFAULT_CATALOG, DEFAULT_MIRROR, DEFAULT_WORKERS, download_corpus


class Command(BaseCommand):
    help = "Download the books of the corpus from a Project Gutenberg mirror."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--count",
            type=int,
            default=int(os.environ.get("CORPUS_SIZE") or CORPUS_SIZE),
            help="Number of books the corpus must hold (default: $CORPUS_SIZE)",
        )
        parser.add_argument("--min-words", type=int, default=MIN_WORDS_PER_BOOK)
        parser.add_argument("--language", default="en", help="Catalog language code")
        parser.add_argument(
            "--catalog", default=DEFAULT_CATALOG, help="Address of pg_catalog.csv.gz"
        )
        parser.add_argument(
            "--mirror", default=DEFAULT_MIRROR, help="Mirror of the main collection"
        )
        parser.add_argument(
            "--delay", type=float, default=0.2, help="Seconds between two requests"
        )

        parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)

    def handle(self, *args: Any, **options: Any) -> None:
        if options["workers"] < 1 or options["delay"] < 0:
            raise CommandError("--workers must be positive and --delay must be nonnegative.")
        summary = download_corpus(
            settings.CORPUS_DIR,
            options["count"],
            options["min_words"],
            print,
            catalog=options["catalog"],
            mirror=options["mirror"],
            language=options["language"],
            delay=options["delay"],
            workers=options["workers"],
        )
        print(
            self.style.SUCCESS(
                f"{summary.books} books in {settings.CORPUS_DIR} "
                f"({summary.downloaded} downloaded, {summary.rejected} skipped)."
            )
        )
        if summary.books < MIN_BOOKS:
            print(
                self.style.WARNING(
                    f"The assignment requires at least {MIN_BOOKS} books."
                )
            )
