web: gunicorn -b 0.0.0.0:$PORT app:app --workers 1 --threads 2
worker: celery -A tasks worker --concurrency=1 --max-tasks-per-child=100 --loglevel=info
