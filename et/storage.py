from __future__ import annotations

import csv
import sqlite3
import threading
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple


@dataclass(slots=True)
class _Paths:
    db: Path
    csv_gaze: Optional[Path]
    csv_sync: Optional[Path]


class ETStorage:
    """
    Schreibt neue Tabellen in dieselbe events_*.sqlite3:
    - gaze_samples(session_id, player, x, y, conf, t_device_ns, t_host_ns, t_mono_ns, t_utc_iso)
    - sync_pairs(session_id, player, kind, t_host_ns, t_device_ns, delta_ns, created_utc)
    CSVs optional.
    """

    def __init__(self, db_path: str, csv_dir: Optional[str] = None):
        self.paths = _Paths(
            db=Path(db_path),
            csv_gaze=(Path(csv_dir) / "gaze_samples.csv") if csv_dir else None,
            csv_sync=(Path(csv_dir) / "sync_pairs.csv") if csv_dir else None,
        )
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.paths.db), check_same_thread=False)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS gaze_samples(
                  session_id TEXT, player TEXT, x REAL, y REAL, conf REAL,
                  t_device_ns INTEGER, t_host_ns INTEGER, t_mono_ns INTEGER, t_utc_iso TEXT
                )"""
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_pairs(
                  session_id TEXT, player TEXT, kind TEXT,
                  t_host_ns INTEGER, t_device_ns INTEGER, delta_ns INTEGER, created_utc TEXT
                )"""
            )
            self._conn.commit()

    def write_gaze(self, rows: Iterable[Tuple[Any, ...]]) -> None:
        with self._lock:
            self._conn.executemany("INSERT INTO gaze_samples VALUES (?,?,?,?,?,?,?,?,?)", list(rows))
            self._conn.commit()
        if self.paths.csv_gaze:
            with self.paths.csv_gaze.open("a", encoding="utf-8", newline="") as fp:
                csv.writer(fp).writerows(rows)

    def write_sync(self, rows: Iterable[Tuple[Any, ...]]) -> None:
        with self._lock:
            self._conn.executemany("INSERT INTO sync_pairs VALUES (?,?,?,?,?,?,?)", list(rows))
            self._conn.commit()
        if self.paths.csv_sync:
            with self.paths.csv_sync.open("a", encoding="utf-8", newline="") as fp:
                csv.writer(fp).writerows(rows)

    def write_single_sync(
        self,
        session_id: str,
        player: str,
        kind: str,
        t_host_ns: int,
        t_device_ns: int,
    ) -> None:
        delta = int(t_device_ns) - int(t_host_ns)
        row = (
            session_id,
            player,
            kind,
            int(t_host_ns),
            int(t_device_ns),
            delta,
            datetime.now(timezone.utc).isoformat(),
        )
        self.write_sync([row])
