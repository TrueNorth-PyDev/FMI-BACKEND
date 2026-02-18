#!/bin/sh
# Start the RQ Scheduler in the background
python manage.py rqscheduler &

# Start the RQ Worker in the background
# We run this in the background too because the main startCommand needs to proceed to gunicorn
python manage.py rqworker default &
