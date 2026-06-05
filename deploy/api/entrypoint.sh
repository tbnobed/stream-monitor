#!/usr/bin/env bash
set -e

# Block until PostgreSQL accepts connections so create_all()/seeding don't crash
# on a cold start where the DB container isn't ready yet.
echo "Waiting for database to become available..."
python - <<'PY'
import os, sys, time
import psycopg2

url = os.environ.get("DATABASE_URL", "")
if not url:
    print("DATABASE_URL is not set", file=sys.stderr)
    sys.exit(1)

for attempt in range(1, 61):
    try:
        psycopg2.connect(url).close()
        print("Database is ready.")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"  attempt {attempt}/60: database not ready ({exc})")
        time.sleep(2)

print("Database did not become ready in time.", file=sys.stderr)
sys.exit(1)
PY

exec "$@"
