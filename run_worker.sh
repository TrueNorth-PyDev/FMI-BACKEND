#!/bin/sh
# Register recurring jobs in Redis (idempotent — clears stale jobs first)
python manage.py setup_periodic_tasks

# Start the RQ Scheduler in the background
python manage.py rqscheduler &

# Start the RQ Worker in the background
python manage.py rqworker default &
