"""Session context-manager fakes for task tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


def session_context(db: Any):
    """Return a no-arg context manager yielding ``db``."""

    @contextmanager
    def _factory() -> Iterator[Any]:
        yield db

    return _factory


def org_session_context(db: Any, captured_org_ids: list[Any] | None = None):
    """Return a ``session_for_org``-shaped context manager yielding ``db``."""

    @contextmanager
    def _factory(org_id: Any) -> Iterator[Any]:
        if captured_org_ids is not None:
            captured_org_ids.append(org_id)
        yield db

    return _factory


def org_session_sequence(dbs: list[Any], captured_org_ids: list[Any] | None = None):
    """Return a ``session_for_org`` fake that yields one db per call."""
    db_iter = iter(dbs)

    @contextmanager
    def _factory(org_id: Any) -> Iterator[Any]:
        if captured_org_ids is not None:
            captured_org_ids.append(org_id)
        yield next(db_iter)

    return _factory
