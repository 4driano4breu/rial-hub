web: flask db upgrade && flask seed-auto && flask r2-pull && gunicorn --workers 2 --bind 0.0.0.0:$PORT --timeout 120 run:app
