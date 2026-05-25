"""Compatibility wrapper for legacy scripts.

New code should import from `backend.utils.db` directly. This module remains so
old standalone scripts do not need their own database connector.
"""

from backend.utils.db import get_db_connection

__all__ = ["get_db_connection"]
