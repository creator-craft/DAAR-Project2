# DAAR Project 2

A Django REST backend (SQLite, inverted index, Jaccard graph, PageRank) behind an Nginx container that also serves the static frontend. The backend code is in `backend/library/`.

## Run

Install Docker with Compose, then:

```sh
docker compose up --build -d
```

Open http://localhost:8080.
Set `FRONTEND_PORT` and `DJANGO_SECRET_KEY` in a root `.env` file (see `.env.example`).

## Build the library

You can copy existing book with:

```sh
docker compose cp ./my_books/. backend:/data/corpus
```

Build the library index for each book named `<gutenberg id>.txt` in `backend/data/corpus`:

```sh
docker compose exec backend python manage.py build_index
```

## API

| Endpoint | Description |
| --- | --- |
| `GET /api/stats` | `books`, `words`, `terms`, `graph`, `corpus_ready` |
| `GET /api/search?q=&mode=keyword\|regex&ranking=pagerank\|frequency&page=` | Search, ranking, recommendations |

Errors are JSON: `{"error": "message"}` with a 4xx status.

## How it works

- **Index**: every word (letters only, 2–30 characters, lowercase) of the book body becomes a `Term`. A `Posting` stores its number of occurrences in a `Book`.
- **Keyword search**: exact lookup of the word in the term table.
- **Advanced search**: the regular expression is matched against whole indexed words (case-insensitive) with [RE2](https://github.com/google/re2) (linear time).
- **Ranking**: `frequency` orders by total occurrences of the matched words. `pagerank` orders by PageRank, then by occurrences.
- **Jaccard graph**: the Jaccard similarity of two books is the size of the intersection of their vocabularies over the size of their union.
  Each book is linked to its 10 most similar books. PageRank is computed on this similarity-weighted directed graph.
- **Recommendations**: the books closest in the graph to the 3 best results.

See [frontend/README.md](frontend/README.md) for the frontend alone and the API contract.
