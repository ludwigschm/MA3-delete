"""Central marker distribution hub for LSL and UDP annotations."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import itertools
import json
import logging
import contextlib
import socket
from queue import Queue, Full, Empty
import threading
from typing import Any, Optional
import time

log = logging.getLogger(__name__)


class MarkerHub:
    """Aggregate experiment markers and forward them to multiple sinks."""

    def __init__(
        self,
        *,
        udp_port: int = 5005,
        queue_maxsize: int = 1000,
    ) -> None:
        self._udp_port = udp_port
        self._queue: Queue[dict[str, Any]] = Queue(maxsize=queue_maxsize)
        self._sentinel: object = object()
        self._seq = itertools.count(1)
        self._counts: dict[str, int] = defaultdict(int)
        self._counts_lock = threading.Lock()
        self._udp_socket = self._create_udp_socket()
        self._lsl_outlet = self._create_lsl_outlet()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="MarkerHub",
            daemon=True,
        )
        self._worker.start()

    # ------------------------------------------------------------------
    def emit(self, kind: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Create a marker event and enqueue it for distribution."""

        event = {
            "seq": next(self._seq),
            "t_local_ns": time.perf_counter_ns(),
            "t_utc_iso": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "payload": payload or {},
        }
        with self._counts_lock:
            self._counts[kind] += 1
        try:
            self._queue.put_nowait(event)
        except Full:
            log.warning("Marker queue saturated – dropping %s", kind)
        return event

    def counts(self) -> dict[str, int]:
        """Return a snapshot of how many markers of each kind were emitted."""

        with self._counts_lock:
            return dict(self._counts)

    def shutdown(self) -> None:
        """Signal the worker thread to terminate and release resources."""

        try:
            self._queue.put_nowait({"kind": "__stop__"})
        except Full:
            self._queue.put({"kind": "__stop__"})
        self._worker.join(timeout=2.0)
        if self._udp_socket is not None:
            with contextlib.suppress(Exception):
                self._udp_socket.close()
        self._udp_socket = None
        self._lsl_outlet = None

    # ------------------------------------------------------------------
    def _create_udp_socket(self) -> Optional[socket.socket]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setblocking(False)
            return sock
        except OSError:
            log.warning("Failed to initialise UDP broadcast socket", exc_info=True)
            return None

    def _create_lsl_outlet(self):  # pragma: no cover - optional dependency
        try:
            from pylsl import StreamInfo, StreamOutlet
        except Exception:
            log.info("pylsl not available – LSL markers disabled")
            return None
        info = StreamInfo(
            name="TabletopMarkers",
            type="Markers",
            channel_count=1,
            nominal_srate=0.0,
            channel_format="string",
            source_id="tabletop_markers_v1",
        )
        info.desc().append_child_value("manufacturer", "MA3 Tabletop")
        return StreamOutlet(info, chunk_size=1, max_buffered=36)

    def _worker_loop(self) -> None:
        while True:
            try:
                event = self._queue.get(timeout=0.5)
            except Empty:
                continue
            if event.get("kind") == "__stop__":
                self._queue.task_done()
                break
            self._distribute(event)
            self._queue.task_done()

    def _distribute(self, event: dict[str, Any]) -> None:
        encoded = json.dumps(event, ensure_ascii=False)
        self._send_udp(encoded)
        self._send_lsl(encoded, event)
        # TODO: Provide hook for optional hardware strobe integration.

    def _send_udp(self, payload: str) -> None:
        if self._udp_socket is None:
            return
        try:
            self._udp_socket.sendto(payload.encode("utf-8"), ("<broadcast>", self._udp_port))
        except OSError:
            log.warning("UDP marker broadcast failed", exc_info=True)

    def _send_lsl(self, payload: str, event: dict[str, Any]) -> None:  # pragma: no cover
        if self._lsl_outlet is None:
            return
        try:
            timestamp = event["t_local_ns"] / 1_000_000_000.0
            self._lsl_outlet.push_sample([payload], timestamp=timestamp)
        except Exception:
            log.warning("Failed to push LSL marker", exc_info=True)
