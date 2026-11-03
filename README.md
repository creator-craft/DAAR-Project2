# DAAR Project 2

## Run the frontend with Docker

Install Docker with Compose and start the Docker engine (Docker Desktop on
Windows, using Linux containers). From the repository root:

```sh
docker compose up --build -d frontend
```

Open http://localhost:8080. Set `FRONTEND_PORT` in a root `.env` file to change
the host port; `.env.example` lists the default.

```sh
docker compose ps
docker compose logs frontend
docker compose down
```

The image serves the static frontend with Nginx and checks `/healthz` for
container health. Rebuild after changing frontend files. Search and collection
statistics require a backend API that is not implemented yet; `/api/` currently
returns HTTP 503 with a JSON error.

See [frontend/README.md](frontend/README.md) for a preview without Docker,
standalone image commands, and the expected API contract.
