"""Regression test for the real cross-thread SQLite bug found live
2026-10-13: every scheduled hourly/daily job silently failed from its very
first tick because APScheduler runs the job on a different thread than the
one that created app.conn - see the docstring on db/database.py's connect().
"""
from __future__ import annotations

import threading

from src.db.database import init_db


def test_a_connection_from_init_db_can_be_used_from_a_different_thread(tmp_path):
    conn = init_db(tmp_path / "test.db")

    errors: list[Exception] = []

    def use_from_another_thread():
        try:
            conn.execute("SELECT 1").fetchone()
        except Exception as exc:  # noqa: BLE001 - captured to assert on below
            errors.append(exc)

    # This is exactly BackgroundScheduler's shape: the connection is created
    # on the main thread (here, by init_db() above) and then used from a
    # worker thread (here, this one) - the same pattern main.py's
    # `lambda: run_hourly(app)` hits on every scheduled tick.
    thread = threading.Thread(target=use_from_another_thread)
    thread.start()
    thread.join()

    assert errors == [], f"cross-thread use raised: {errors}"
