
all:

run:
	docker compose up --build -d

# Only when docker runs:

use_files:
	docker compose cp ./backend/data/corpus/. backend:/data/corpus

build_index:
	docker compose exec backend python manage.py build_index

stop:
	docker compose down