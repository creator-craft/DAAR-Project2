from django.db import models


class Book(models.Model):
    id = models.PositiveIntegerField(
        primary_key=True, help_text="Project Gutenberg identifier"
    )
    title = models.CharField(max_length=512)
    author = models.CharField(max_length=256)
    word_count = models.PositiveIntegerField()
    pagerank = models.FloatField(default=0.0)

    def __str__(self) -> str:
        return f"{self.title} ({self.id})"


class Term(models.Model):
    word = models.CharField(max_length=32, unique=True)

    def __str__(self) -> str:
        return self.word


class Posting(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="postings")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="postings")
    occurrences = models.PositiveIntegerField()


class Similarity(models.Model):
    source = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="outgoing")
    target = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="incoming")
    similarity = models.FloatField()
