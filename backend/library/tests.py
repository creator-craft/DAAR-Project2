import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
from django.test import TestCase
from rest_framework.test import APIClient
from scipy.sparse import csr_matrix

from library.constants import PAGE_SIZE
from library.corpus import corpus_files, parse_book
from library.graph import Edge, jaccard_similarity, nearest_edges, pagerank
from library.indexing import rebuild_index

COMMON = "the and of to in that was with for his"


def gutenberg_text(title: str, author: str, body: str) -> str:
    return (
        f"The Project Gutenberg eBook of {title}\n\nTitle: {title}\n\nAuthor: {author}\n\nLanguage: English\n\n"
        f"*** START OF THE PROJECT GUTENBERG EBOOK {title.upper()} ***\n{body}\n"
        f"*** END OF THE PROJECT GUTENBERG EBOOK {title.upper()} ***\nlicense words ignored\n"
    )


class ParsingTests(TestCase):
    def test_parse_book_reads_header_and_ignores_boilerplate(self) -> None:
        book = parse_book(
            gutenberg_text("Moby", "Melville, Herman", "whale whale sea I a")
        )
        self.assertEqual(
            (book.title, book.author, book.language),
            ("Moby", "Melville, Herman", "English"),
        )
        self.assertEqual(dict(book.frequencies), {"whale": 2, "sea": 1})
        self.assertEqual(book.word_count, 3)


class GraphTests(TestCase):
    def test_jaccard_similarity(self) -> None:
        incidence = csr_matrix(
            np.array([[1, 1, 0], [0, 1, 1], [0, 0, 0]], dtype=np.int32)
        )
        similarity = jaccard_similarity(incidence)
        self.assertAlmostEqual(similarity[0, 1], 1 / 3)
        self.assertEqual(similarity[0, 2], 0.0)

    def test_nearest_edges_skip_disjoint_books(self) -> None:
        similarity = np.array([[1.0, 0.5, 0.0], [0.5, 1.0, 0.0], [0.0, 0.0, 1.0]])
        self.assertEqual(
            nearest_edges(similarity, 2), [Edge(0, 1, 0.5), Edge(1, 0, 0.5)]
        )

    def test_pagerank_favours_the_most_linked_book(self) -> None:
        edges = [Edge(0, 2, 1.0), Edge(1, 2, 1.0), Edge(2, 0, 1.0)]
        ranks = pagerank(3, edges)
        self.assertAlmostEqual(float(ranks.sum()), 1.0)
        self.assertEqual(int(ranks.argmax()), 2)


class ApiTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        books = {
            1: ("Sea Tales", "A. Sailor", "ocean ocean ocean sea ship wave"),
            2: ("Deep Water", "B. Diver", "ocean sea sea sea ship coral"),
            3: ("Star Road", "C. Pilot", "rocket star planet orbit moon ship"),
            4: ("Red Planet", "D. Rover", "planet planet planet mars rocket crater"),
        }
        with tempfile.TemporaryDirectory() as directory:
            for identifier, (title, author, words) in books.items():
                body = " ".join([words, COMMON] * 3)
                (Path(directory) / f"{identifier}.txt").write_text(
                    gutenberg_text(title, author, body)
                )
            rebuild_index(
                corpus_files(Path(directory)), min_words=1, report=lambda _: None
            )

    def setUp(self) -> None:
        self.client = APIClient()

    def search(self, **params: str | int) -> dict[str, Any]:
        response = self.client.get("/api/search", params)
        self.assertEqual(response.status_code, 200, response.content)
        return dict(response.json())

    def test_stats(self) -> None:
        data = self.client.get("/api/stats").json()
        self.assertEqual(
            (data["books"], data["graph"], data["corpus_ready"]), (4, True, False)
        )
        self.assertGreater(data["terms"], 10)

    def test_keyword_search_ranks_by_frequency(self) -> None:
        data = self.search(q="Ocean", ranking="frequency")
        self.assertEqual([book["id"] for book in data["results"]], [1, 2])
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["page_size"], PAGE_SIZE)
        self.assertNotIn("matched_terms", data)

    def test_keyword_search_ranks_by_pagerank(self) -> None:
        data = self.search(q="ship", ranking="pagerank")
        ranks = [book["pagerank"] for book in data["results"]]
        self.assertEqual(ranks, sorted(ranks, reverse=True))
        self.assertEqual(data["total"], 3)

    def test_regex_search_matches_whole_words_case_insensitively(self) -> None:
        data = self.search(q="PLAN.T|moo+n?", mode="regex", ranking="frequency")
        self.assertEqual(data["matched_terms"], ["moon", "planet"])
        self.assertEqual(data["matched_term_count"], 2)
        self.assertEqual([book["id"] for book in data["results"]], [4, 3])

    def test_recommendations_are_neighbours_of_top_results(self) -> None:
        data = self.search(q="ocean", ranking="frequency")
        recommended = {book["id"] for book in data["recommendations"]}
        self.assertEqual(recommended, {3, 4})

    def test_unknown_word_returns_no_result(self) -> None:
        data = self.search(q="zzz")
        self.assertEqual(
            (data["total"], data["results"], data["recommendations"]), (0, [], [])
        )

    def test_regex_matching_too_many_words_is_rejected(self) -> None:
        with patch("library.search.MAX_REGEX_TERMS", 3):
            response = self.client.get("/api/search", {"q": ".*", "mode": "regex"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("too broad", response.json()["error"])

    def test_errors_are_json_with_an_error_message(self) -> None:
        bad_requests: list[dict[str, str | int]] = [
            {},
            {"q": "sea", "mode": "fuzzy"},
            {"q": "(sea", "mode": "regex"},
            {"q": r"(?=sea)", "mode": "regex"},
            {"q": r"\d+", "mode": "regex"},
            {"q": "sea", "page": 9},
            {"q": "sea", "page": 0},
            {"q": "x" * 129},
        ]
        for params in bad_requests:
            response = self.client.get("/api/search", params)
            self.assertEqual(response.status_code, 400, params)
            self.assertIsInstance(response.json()["error"], str)
