
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

stop:
	docker compose down
