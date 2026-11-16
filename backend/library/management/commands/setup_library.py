from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand

from library.models import Book


class Command(BaseCommand):
    help = "Download the corpus and build the index, unless the library is already indexed."

    def handle(self, *args: Any, **options: Any) -> None:
        if Book.objects.exists():
            print("Library already indexed, nothing to set up.")
            return
        # An interrupted download resumes, and an interrupted indexing is rolled back
        call_command("download_corpus")
        call_command("build_index")
