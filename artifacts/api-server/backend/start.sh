#!/bin/bash
set -e
cd "$(dirname "$0")"

# Install Python dependencies if needed
if [ ! -f .deps_installed ] || [ requirements.txt -nt .deps_installed ]; then
  pip install -q -r requirements.txt
  touch .deps_installed
fi

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8080}" --reload --log-level info
