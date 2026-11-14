# Margin frontend

The frontend is imported from `Daar-project-2-mine/web` and lives in the
existing `public/` directory. It uses plain HTML, CSS, and JavaScript, with no
package installation or build step.

## Docker

From the repository root, build and start the frontend:

```sh
docker compose up --build -d frontend
```

Open http://localhost:8080. Docker must be running with Linux containers.
The default host port is 8080; set `FRONTEND_PORT` in a root `.env` file to
override it. Stop the service with `docker compose down`.

To build and run without Compose:

```sh
docker build -t daar-frontend ./frontend
docker run --rm -p 8080:80 daar-frontend
```

The image uses the [official Nginx image](https://hub.docker.com/_/nginx) to
serve `public/`, with no build dependencies. Files are copied into the image,
so rebuild after edits. `/healthz` returns HTTP 200 and is used by Docker's
health check. Unknown static paths return HTTP 404. `/api/` is proxied to the
`backend` service of the Compose file; when it is unreachable (for example with
the standalone commands above), Nginx answers HTTP 503 with a JSON `error`
message.

## Preview without Docker

From the repository root:

```sh
python -m http.server 8080 --directory frontend/public
```

Open http://localhost:8080. This serves the interface and its assets. Search and
collection statistics require the API described below; the static preview alone
will display connection errors for those features.

## Backend integration

Nginx serves `public/` at `/` and proxies `/api/` to the Django backend on the
same origin. The backend is described in the root [README](../README.md).

- `GET /api/stats` returns `books`, `words`, `terms`, `graph` (boolean), and
  `corpus_ready` (boolean).
- `GET /api/search?q=ocean&mode=keyword&ranking=pagerank&page=1` returns `query`,
  `mode`, `total`, `elapsed_ms`, `page_size`, `graph_ready`, `results`, and
  `recommendations`. Modes are `keyword` and `regex`; rankings are `pagerank`
  and `frequency`.
- Each result has `id` (Gutenberg ID), `title`, `author`, `occurrences`, and
  `pagerank` (number). Recommendations have `id`, `title`, `author`, and
  `similarity` (number).
- Regex responses also include `matched_term_count` and `matched_terms` (an
  array of words).
- `matched_terms` lists at most 30 words (alphabetical), while `matched_term_count`
  is the total number of matching indexed words. Expressions matching more than
  5,000 words are rejected with an error.
- API errors use a non-success HTTP status and a JSON `error` message.

The interface includes keyword and regex search, ranking selection, pagination,
recommendations, Gutenberg links, and responsive desktop/mobile layouts.
