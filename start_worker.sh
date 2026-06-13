#!/bin/sh
python -m http.server $PORT &
exec arq app.worker.WorkerSettings
