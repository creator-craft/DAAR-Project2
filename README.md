# DAAR Project 2

A Django REST backend (SQLite, inverted index, Jaccard graph, PageRank) behind an Nginx container that also serves the static frontend. The backend code is in `backend/library/`.

## Run

Install Docker with Compose, then:

```sh
docker compose up --build -d
```

Open http://localhost:8080, or `http://<server address>:8080` from another machine of the same network.

On the first start, the backend builds the library in the background: it downloads the corpus
(about 760 MB, 7 minutes), then indexes it (about 2 minutes). The site answers during that time
and shows the number of indexed books once the library is ready. Follow the progress with:

```sh
docker compose logs -f backend
```

The next starts reuse the `corpus` and `db` volumes. `docker compose down -v` deletes them.

## Configuration

Copy `.env.example` to `.env` to change the defaults. `.env` is ignored by Git and Docker.

| Variable | Default | Description |
| --- | --- | --- |
| `FRONTEND_PORT` | `8080` | Port published on the host |
| `DJANGO_SECRET_KEY` | development key | Secret key of Django |
| `CORPUS_SIZE` | `1700` | Number of books downloaded on the first start |

## Containers

- `frontend` (Nginx) serves the static site and forwards `/api/` to `http://backend:8000`. It is the only published service.
- `backend` (Django) publishes no port. It is reachable by its service name from the `library-net` bridge network only.
- The `corpus` volume holds the downloaded books and the `db` volume holds the SQLite index.

## Corpus

The assignment requires at least 1664 books of at least 10,000 words each.

```sh
docker compose exec backend python manage.py download_corpus
docker compose exec backend python manage.py build_index
```

- `download_corpus` reads the official Project Gutenberg catalog (`pg_catalog.csv.gz`) and takes the English
  books by increasing identifier, so the corpus is reproducible. Project Gutenberg forbids robots on
  www.gutenberg.org, so the catalog and the texts are fetched from mirrors (`--catalog`, `--mirror`).
- A book is kept when its body is delimited by the Gutenberg markers and counts at least 10,000 words.
  It is saved as `<gutenberg id>.txt` in `/data/corpus`. Rejected identifiers are remembered, so an
  interrupted download resumes where it stopped.
- `build_index` rebuilds the inverted index, the Jaccard graph and the PageRank from `/data/corpus`.

Your own `<gutenberg id>.txt` files can be added with `docker compose cp ./my_books/. backend:/data/corpus`
before running `build_index`.

## API

| Endpoint | Description |
| --- | --- |
| `GET /api/stats` | `books`, `words`, `terms`, `graph`, `corpus_ready` |
| `GET /api/search?q=&mode=keyword\|regex&ranking=pagerank\|frequency&page=` | Search, ranking, recommendations |

Errors are JSON: `{"error": "message"}` with a 4xx status.

## Performance benchmark

```sh
make benchmark   # requires the indexed corpus and, on the host, `pip install matplotlib`
```

`python manage.py benchmark` draws nested random samples of the corpus (100, 200, 400, 800, 1200 books and
the whole corpus, fixed seed `--seed 2026`). Each sample is indexed from scratch into a scratch SQLite file
(`--database`, default `/tmp/benchmark.sqlite3`), so the library served by the site is not modified. It records
the time of every indexing phase (parsing, posting inserts, Jaccard matrix, nearest neighbours, PageRank) and
the size of the index in `indexing.csv`, then replays a fixed set of keyword and RegEx queries with both rankings
(one warm-up, then `--repeat 5` timed runs each) and records every run in `queries.csv`.
`docs/benchmark/plot.py` turns both files into the charts of the report and `summary.md`.

`make stress` runs `docs/benchmark/stress.py` on the host: from 1 to 32 concurrent clients (8 for RegEx),
it sends a fixed batch of searches through Nginx and records the throughput and the latency in `stress.csv`.

## Relevance test

```sh
make relevance
```

`python manage.py relevance` uses the Project Gutenberg catalog downloaded with the corpus as reference:
a book is relevant to a query when one of its Subjects or Bookshelves contains the query word. For 15 queries
(5 topics labelled on at least 50 books, 10 on 10 to 30 books), it records the first 10 results of both rankings
(`results.csv`), their precision, the precision of a random order of the same results and the precision of the
recommendations (`summary.csv`). `docs/relevance/plot.py` draws the chart of the report and `summary.md`.

## How it works

- **Index**: every word (letters only, 2–30 characters, lowercase) of the book body becomes a `Term`. A `Posting` stores its number of occurrences in a `Book`.
- **Keyword search**: exact lookup of the word in the term table.
- **Advanced search**: the regular expression is matched against whole indexed words (case-insensitive) with [RE2](https://github.com/google/re2) (linear time).
- **Ranking**: `frequency` orders by total occurrences of the matched words. `pagerank` orders by PageRank, then by occurrences.
- **Jaccard graph**: the Jaccard similarity of two books is the size of the intersection of their vocabularies over the size of their union.
  Each book is linked to its 10 most similar books. PageRank is computed on this similarity-weighted directed graph.
- **Recommendations**: the books closest in the graph to the 3 best results.

See [frontend/README.md](frontend/README.md) for the frontend alone and the API contract.
