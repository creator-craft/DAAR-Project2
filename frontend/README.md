# Margin frontend

The frontend is imported from `Daar-project-2-mine/web` and lives in the
existing `public/` directory. It uses plain HTML, CSS, and JavaScript, with no
package installation or build step.

## Preview

From the repository root:

```powershell
python -m http.server 8080 --directory frontend/public
```

Open http://localhost:8080. This serves the interface and its assets. Search and
collection statistics require the API described below; the static preview alone
will display connection errors for those features.

## Backend integration

Serve `public/` at `/` and expose the API on the same origin. The existing Django
backend currently only defines `/admin/`; frontend migration does not change it.

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
- API errors should use a non-success HTTP status and a JSON `error` message.

The interface includes keyword and regex search, ranking selection, pagination,
recommendations, Gutenberg links, and responsive desktop/mobile layouts.
