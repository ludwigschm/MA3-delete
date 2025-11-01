"""Async coordination layer for controlling Pupil Labs Neon devices.

The concrete REST/gRPC endpoints for starting, stopping and annotating Neon
recordings are not available yet.  The manager therefore exposes a single
queue-backed worker that attempts to perform the remote call via placeholder
functions.  Whenever these calls are not implemented or fail, the command is
persisted to ``logs/neon_cmds.jsonl`` to ensure we never lose intent
information.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from queue import Queue, Full, Empty
import threading
from typing import Any, Iterable, Optional
import time
import requests  # NEW

log = logging.getLogger(__name__)


@dataclass(slots=True)
class NeonDevice:
    """Connection information for a single Neon headset."""

    id: str
    host: str
    port: int = 0
    label: str = ""


class EyeTrackerManager:
    """Coordinate start/stop and annotation commands for Neon devices."""

    def __init__(
        self,
        devices: Iterable[NeonDevice],
        *,
        queue_maxsize: int = 1000,
        fallback_path: Optional[Path] = None,
    ) -> None:
        self._devices: list[NeonDevice] = list(devices)
        self._queue: Queue[tuple[object, Optional[NeonDevice], dict[str, Any]]] = Queue(
            maxsize=queue_maxsize
        )
        self._sentinel: object = object()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="NeonEyeTrackerManager",
            daemon=True,
        )
        self._worker.start()
        self._active_session: Optional[str] = None
        self._fallback_path = (
            fallback_path if fallback_path is not None else Path("logs") / "neon_cmds.jsonl"
        )
        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    def start_all(self, session_id: str) -> None:
        """Start recording on all configured devices asynchronously."""

        self._active_session = session_id
        payload = {"session_id": session_id}
        log.info("Enqueue start_all for all Neon devices (session=%s)", session_id)
        self._broadcast_command("start", payload)

    def stop_all(self) -> None:
        """Stop recording on all configured devices asynchronously."""

        payload = {"session_id": self._active_session}
        log.info("Enqueue stop_all for all Neon devices")
        self._broadcast_command("stop", payload)
        self._active_session = None

    def annotate(self, label: str, payload: dict[str, Any]) -> None:
        """Send an annotation to all active devices without blocking."""

        combined = {"label": label, "payload": payload}
        if self._active_session:
            combined["session_id"] = self._active_session
        log.info("Enqueue annotate for all Neon devices: %s", label)
        self._broadcast_command("annotate", combined)

    def shutdown(self) -> None:
        """Stop the background worker thread gracefully."""

        try:
            self._queue.put_nowait((self._sentinel, None, {}))
        except Full:
            # Fall back to a blocking put – shutdown must succeed.
            self._queue.put((self._sentinel, None, {}))
        self._worker.join(timeout=2.0)

    # ------------------------------------------------------------------
    # Internal helpers
    def _broadcast_command(self, command: str, payload: dict[str, Any]) -> None:
        for device in self._devices:
            self._enqueue(command, device, payload)

    def _enqueue(
        self, command: object, device: Optional[NeonDevice], payload: dict[str, Any]
    ) -> None:
        item = (command, device, dict(payload))
        try:
            self._queue.put_nowait(item)
        except Full:
            label = getattr(device, "id", "<unknown>") if device is not None else "<sentinel>"
            log.warning("Neon command queue saturated – dropping %s for %s", command, label)

    def _worker_loop(self) -> None:
        while True:
            try:
                command, device, payload = self._queue.get(timeout=0.5)
            except Empty:
                continue
            log.info("Neon worker received command: %s", command)
            if command is self._sentinel:
                self._queue.task_done()
                break
            handled = False
            try:
                if device is not None:
                    handled = self._dispatch_remote(command, device, payload)
            except Exception:  # pragma: no cover - defensive
                log.exception("Unexpected error dispatching Neon command %s", command)
            if device is not None and not handled:
                self._write_fallback(command, device, payload)
            self._queue.task_done()

    # ------------------------------------------------------------------
    # Remote communication (placeholder)
    def _dispatch_remote(
        self, command: str, device: NeonDevice, payload: dict[str, Any]
    ) -> bool:
        """
        Send command to Neon Companion HTTP API (default port 8080).
        Returns True on HTTP 2xx, otherwise False.
        """
        host = device.host
        port = device.port or 8080
        base = f"http://{host}:{port}/api"

        try:
            if command == "start":
                url = f"{base}/recording:start"
                r = requests.post(
                    url,
                    json={"session_id": payload.get("session_id", "")},
                    timeout=2.0,
                )
                log.info(
                    "Neon start → %s (%s): %s %s",
                    device.label or device.id,
                    host,
                    r.status_code,
                    r.text[:200],
                )
                r.raise_for_status()
                return True

            elif command == "stop":
                url = f"{base}/recording:stop_and_save"
                r = requests.post(url, json={}, timeout=2.0)
                log.info(
                    "Neon stop  → %s (%s): %s %s",
                    device.label or device.id,
                    host,
                    r.status_code,
                    r.text[:200],
                )
                r.raise_for_status()
                return True

            elif command == "annotate":
                label = str(payload.get("label", "event"))
                props = payload.get("payload", {})
                body = {
                    "name": label,
                    "properties": props,
                    # Optional: "timestamp_ns": time.time_ns(),
                }
                url = f"{base}/event"
                r = requests.post(url, json=body, timeout=2.0)
                log.info(
                    "Neon event → %s (%s): %s %s",
                    device.label or device.id,
                    host,
                    r.status_code,
                    r.text[:200],
                )
                r.raise_for_status()
                return True

            return False

        except requests.RequestException as e:
            log.error(
                "Neon HTTP %s FAILED on %s (%s): %s",
                command,
                device.label or device.id,
                host,
                e,
            )
            return False


    # ------------------------------------------------------------------
    # Fallback logging
    def _write_fallback(self, command: str, device: NeonDevice, payload: dict[str, Any]) -> None:
        entry = {
            "timestamp_ns": time.perf_counter_ns(),
            "t_utc_iso": datetime.now(timezone.utc).isoformat(),
            "command": command,
            "device": {
                "id": device.id,
                "host": device.host,
                "port": device.port,
                "label": device.label,
            },
            "payload": payload,
        }
        try:
            with self._fallback_path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            log.exception("Failed to write Neon command fallback entry")
