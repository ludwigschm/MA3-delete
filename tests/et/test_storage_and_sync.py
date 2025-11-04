import os
import sqlite3
import tempfile
import asyncio

from et.storage import ETStorage
from et.sync import NeonTimeSync


def test_etstorage_creates_tables_and_inserts():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "events_test.sqlite3")
        st = ETStorage(db, csv_dir=d)
        st.write_gaze([("s1", "p1", 0.5, 0.5, 1.0, 10, 20, 30, "2025-01-01T00:00:00Z")])
        st.write_sync([("s1", "p1", "fix.flash_start", 20, 10, -10, "2025-01-01T00:00:00Z")])
        conn = sqlite3.connect(db)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM gaze_samples")
        assert c.fetchone()[0] == 1
        c.execute("SELECT COUNT(*) FROM sync_pairs")
        assert c.fetchone()[0] == 1


def test_neon_time_sync_uses_measure_fn():
    async def measure(n, timeout):
        return [0.010, 0.020, 0.015]

    ts = NeonTimeSync("dev", measure)
    off = asyncio.run(ts.initial())
    assert 0.009 <= off <= 0.021
