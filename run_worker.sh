#!/bin/sh
# Background job runner: RQ scheduler + worker.
# The worker stays in the foreground so this script runs as long as the worker
# does (required when it is its own process, e.g. the Procfile `worker` entry).
set -e

# Register recurring jobs in Redis (idempotent — clears stale jobs first)
python manage.py setup_periodic_tasks

# The scheduler enqueues periodic jobs; the worker executes them
python manage.py rqscheduler &
exec python manage.py rqworker default
