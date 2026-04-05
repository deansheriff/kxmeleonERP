"""
External monitoring integrations — Loki log shipping and GlitchTip error tracking.

Wires up:
- ResilientLokiHandler: pushes structured logs to a Grafana Loki instance
  with automatic session recovery, connection timeouts, and backoff.
- sentry-sdk: captures exceptions and sends them to GlitchTip (Sentry-compatible)

Both are optional — if the relevant env vars are empty the integration is silently skipped.
"""

from __future__ import annotations

import json
import logging
import os
import time
from logging.handlers import QueueHandler, QueueListener
from queue import Queue
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state for health reporting
# ---------------------------------------------------------------------------
_loki_stats: dict[str, Any] = {
    "enabled": False,
    "url": "",
    "sent": 0,
    "dropped": 0,
    "last_error": "",
    "last_success_ts": 0.0,
    "consecutive_failures": 0,
}
_loki_stats_lock = Lock()
_sentry_enabled = False
_sentry_dsn = ""


def get_monitoring_status() -> dict[str, Any]:
    """Return current monitoring health for the ``/health/monitoring`` endpoint."""
    with _loki_stats_lock:
        loki = dict(_loki_stats)

    sentry_status: dict[str, Any] = {"enabled": _sentry_enabled}
    if _sentry_enabled:
        try:
            import sentry_sdk

            client = sentry_sdk.get_client()
            sentry_status["dsn_configured"] = client.dsn is not None
            sentry_status["transport_healthy"] = True
        except Exception as exc:
            sentry_status["dsn_configured"] = False
            sentry_status["transport_healthy"] = False
            sentry_status["error"] = str(exc)[:200]

    return {"loki": loki, "sentry": sentry_status}


# ---------------------------------------------------------------------------
# Resilient Loki handler (replaces python-logging-loki)
# ---------------------------------------------------------------------------

_LOKI_CONNECT_TIMEOUT = 5  # seconds
_LOKI_READ_TIMEOUT = 10  # seconds
_BACKOFF_BASE = 2.0  # exponential backoff base
_BACKOFF_MAX = 120.0  # max seconds between retries


class ResilientLokiHandler(logging.Handler):
    """Pushes log records to Loki's ``/loki/api/v1/push`` endpoint.

    Unlike ``python-logging-loki``, this handler:
    - Uses explicit connection and read timeouts (no infinite waits).
    - Recreates the HTTP session on failure instead of closing permanently.
    - Applies exponential backoff when the endpoint is unreachable.
    - Tracks delivery stats for health-check reporting.
    """

    def __init__(
        self,
        url: str,
        tags: dict[str, str],
        *,
        connect_timeout: float = _LOKI_CONNECT_TIMEOUT,
        read_timeout: float = _LOKI_READ_TIMEOUT,
    ) -> None:
        super().__init__()
        self.url = url
        self.tags = tags
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout

        self._session = self._new_session()
        self._consecutive_failures = 0
        self._next_retry_at = 0.0
        self._lock = Lock()

    # -- session management -------------------------------------------------

    @staticmethod
    def _new_session() -> Any:
        import requests  # type: ignore[import-untyped]

        s = requests.Session()
        s.headers["Content-Type"] = "application/json"
        return s

    def _reset_session(self) -> None:
        try:
            self._session.close()
        except Exception:  # noqa: S110 — intentional; session close is best-effort cleanup
            pass  # nosec B110
        self._session = self._new_session()

    # -- Loki payload -------------------------------------------------------

    def _build_payload(self, record: logging.LogRecord) -> str:
        labels = dict(self.tags)
        labels["logger"] = record.name
        labels["severity"] = record.levelname.lower()

        ts_ns = str(int(record.created * 1e9))
        message = self.format(record) if self.formatter else record.getMessage()

        payload: dict[str, Any] = {
            "streams": [
                {
                    "stream": labels,
                    "values": [[ts_ns, message]],
                }
            ]
        }
        return json.dumps(payload)

    # -- emit ---------------------------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        now = time.monotonic()

        # Back off if we're in a failure window
        if now < self._next_retry_at:
            with _loki_stats_lock:
                _loki_stats["dropped"] += 1
            return

        try:
            body = self._build_payload(record)
            resp = self._session.post(
                self.url,
                data=body,
                timeout=(self.connect_timeout, self.read_timeout),
            )
            if resp.status_code < 300:
                with _loki_stats_lock:
                    _loki_stats["sent"] += 1
                    _loki_stats["last_success_ts"] = time.time()
                    _loki_stats["consecutive_failures"] = 0
                    _loki_stats["last_error"] = ""
                self._consecutive_failures = 0
            else:
                self._handle_failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:
            self._handle_failure(str(exc)[:200])

    def _handle_failure(self, error_msg: str) -> None:
        self._consecutive_failures += 1
        backoff = min(_BACKOFF_BASE**self._consecutive_failures, _BACKOFF_MAX)
        self._next_retry_at = time.monotonic() + backoff

        with _loki_stats_lock:
            _loki_stats["dropped"] += 1
            _loki_stats["last_error"] = error_msg
            _loki_stats["consecutive_failures"] = self._consecutive_failures

        # Recreate session so a broken connection doesn't poison future attempts
        self._reset_session()


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _setup_loki(app_name: str, server: str, environment: str, url: str) -> None:
    """Add a resilient Loki push handler to the root logger."""
    global _loki_stats  # noqa: PLW0603 — module-level stats dict

    if not url:
        return

    try:
        import requests  # noqa: F401 — verify dependency available
    except ImportError:
        logger.warning("requests not installed — skipping Loki handler")
        return

    tags = {"app": app_name, "server": server, "environment": environment}
    handler = ResilientLokiHandler(url, tags)

    # Wrap in QueueHandler so emit() runs in a background thread
    # and never blocks the application.
    queue: Queue[logging.LogRecord] = Queue(maxsize=10_000)
    queue_handler = QueueHandler(queue)
    listener = QueueListener(queue, handler, respect_handler_level=True)
    listener.start()

    logging.getLogger().addHandler(queue_handler)

    with _loki_stats_lock:
        _loki_stats["enabled"] = True
        _loki_stats["url"] = url

    logger.info("Loki handler enabled → %s", url)


def _setup_sentry(app_name: str, environment: str, dsn: str) -> None:
    """Initialise Sentry SDK pointing at GlitchTip."""
    global _sentry_enabled, _sentry_dsn  # noqa: PLW0603

    if not dsn:
        return

    try:
        import sentry_sdk
    except ImportError:
        logger.warning("sentry-sdk not installed — skipping GlitchTip integration")
        return

    traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        release=os.getenv("APP_VERSION", ""),
        server_name=app_name,
    )
    _sentry_enabled = True
    _sentry_dsn = dsn
    logger.info("Sentry/GlitchTip enabled for %s (%s)", app_name, environment)


def setup_monitoring(
    app_name: str = "dotmac_erp",
    server: str = "",
    environment: str = "",
    loki_url: str = "",
    glitchtip_dsn: str = "",
) -> None:
    """One-call setup for Loki logging and GlitchTip error tracking.

    Values can be passed directly or read from environment variables.
    Direct arguments take precedence over env vars.

    Args:
        app_name: Label used in Loki tags and Sentry server_name.
        server: Host identifier for Loki tags (e.g. ``"remote-1"``).
            Falls back to ``MONITORING_SERVER`` env var.
        environment: ``"production"`` / ``"staging"`` — falls back to
            ``APP_ENV`` env var then ``"production"``.
        loki_url: Loki push endpoint. Falls back to ``LOKI_URL`` env var.
        glitchtip_dsn: Sentry/GlitchTip DSN. Falls back to ``SENTRY_DSN`` env var.
    """
    if not server:
        server = os.getenv("MONITORING_SERVER", "")
    if not environment:
        environment = os.getenv("APP_ENV", "production")
    if not loki_url:
        loki_url = os.getenv("LOKI_URL", "")
    if not glitchtip_dsn:
        glitchtip_dsn = os.getenv("SENTRY_DSN", "")

    _setup_loki(app_name, server, environment, loki_url)
    _setup_sentry(app_name, environment, glitchtip_dsn)
