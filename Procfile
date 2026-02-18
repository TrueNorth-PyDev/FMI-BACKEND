web: gunicorn privcap_hub.wsgi:application
worker: sh run_worker.sh
d 0.0.0.0:$PORT --log-file -
