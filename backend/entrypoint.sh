#!/bin/sh
set -e

python manage.py migrate --noinput

# On first start, the library is built in the background so that the API answers
# immediately. Follow the progress with `docker compose logs -f backend`.
if [ "${LIBRARY_AUTO_SETUP:-1}" = "1" ]; then
    python -u manage.py setup_library &
fi

exec python manage.py runserver 0.0.0.0:8000 --noreload
