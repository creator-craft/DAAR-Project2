
all:

# Builds the library on the first start (see README)
run:
	docker compose up --build -d

# Only when docker runs:

logs:
	docker compose logs -f backend

download_corpus:
	docker compose exec backend python manage.py download_corpus

use_files:
	docker compose cp ./backend/data/corpus/. backend:/data/corpus

build_index:
	docker compose exec backend python manage.py build_index

test:
	docker compose exec backend python manage.py test library

# Index build and search latency on nested samples (about 10 minutes), then the charts (needs matplotlib)
benchmark:
	docker compose exec backend python manage.py benchmark
	docker compose cp backend:/data/benchmark/. ./docs/benchmark/
	python3 docs/benchmark/plot.py docs/benchmark

# Throughput and latency of the API under concurrent clients, through Nginx (about 8 minutes)
stress:
	python3 docs/benchmark/stress.py --output docs/benchmark
	python3 docs/benchmark/plot.py docs/benchmark

# Precision of the rankings against the labels of the Gutenberg catalog, then the chart (needs matplotlib)
relevance:
	docker compose exec backend python manage.py relevance
	docker compose cp backend:/data/relevance/. ./docs/relevance/
	python3 docs/relevance/plot.py docs/relevance

stop:
	docker compose down
