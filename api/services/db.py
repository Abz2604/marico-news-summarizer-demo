"""Placeholder Snowflake connector.

Phase 0 uses in-memory repositories. This module acts as a placeholder for
future Snowflake connectivity and exposes a minimal interface so call sites
do not change when the real connector is implemented.
"""

from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional


class PlaceholderConnection:
    def __init__(self) -> None:
        self._open = True

    def cursor(self):  # type: ignore[no-untyped-def]
        raise NotImplementedError("Snowflake connector not implemented in Phase 0")

    def close(self) -> None:
        self._open = False


def get_connection() -> PlaceholderConnection:
    return PlaceholderConnection()


@contextmanager
def execute_query(_sql: str, _params: Optional[Dict[str, Any]] = None) -> Generator[None, None, None]:
    """Execute a query (placeholder). Replace with real Snowflake calls later."""

    try:
        yield
    finally:
        pass


