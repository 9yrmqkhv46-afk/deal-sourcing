"""Shared pytest fixtures.

Points ``DATABASE_URL`` at an isolated on-disk SQLite file *before* any test
module imports ``app.db`` / ``app.main`` (conftest.py is always imported
first by pytest), so the test run never touches a developer's local
``deals.db`` and each run starts from a clean database. Tables are created
here too rather than relying on FastAPI's startup event, since
``TestClient(app)`` instantiated without a ``with`` block never runs it.
"""

from __future__ import annotations

import os
import tempfile

_tmp_dir = tempfile.mkdtemp(prefix="deal-sourcing-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test_deals.db"

from app import db  # noqa: E402  (import must follow the env var being set)

db.init_db()
