#!/bin/sh

# Install monitoring dependencies if not already present
python -c "import logging_loki" 2>/dev/null || pip install -q python-logging-loki==0.3.1 rfc3339==6.2 2>/dev/null
python -c "import sentry_sdk" 2>/dev/null || pip install -q "sentry-sdk[fastapi]>=2.0" 2>/dev/null

is_web_command() {
  case "$1" in
    gunicorn|uvicorn)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

seed_admin_user() {
  retries="${SEED_ADMIN_RETRIES:-12}"
  delay="${SEED_ADMIN_RETRY_DELAY_SECONDS:-5}"
  attempt=1

  while [ "$attempt" -le "$retries" ]; do
    echo "Seeding admin user (attempt $attempt/$retries)..."
    if python scripts/seed_admin.py; then
      echo "Admin seed completed."
      return 0
    fi

    attempt=$((attempt + 1))
    if [ "$attempt" -le "$retries" ]; then
      echo "Admin seed failed; retrying in ${delay}s..."
      sleep "$delay"
    fi
  done

  echo "Admin seed failed after $retries attempts."
  return 1
}

if is_web_command "$1"; then
  case "${SEED_ADMIN_ON_START:-true}" in
    false|False|FALSE|0|no|No|NO|off|Off|OFF)
      echo "Admin seed skipped."
      ;;
    *)
      seed_admin_user || exit 1
      ;;
  esac
fi

exec "$@"
