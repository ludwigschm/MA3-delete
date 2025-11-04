from __future__ import annotations

import asyncio
import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional


class NeonError(RuntimeError):
    ...


@dataclass(slots=True)
class NeonEndpoint:
    host: str          # "192.168.1.10"
    port: int = 8080   # HTTP (REST) fallback

    def base(self) -> str:
        return f"http://{self.host}:{self.port}"


class NeonClient:
    """
    Minimaler Neon-Client:
    - Aufnahme starten/stoppen (HTTP Fallback)
    - Marker senden (HTTP /v1/marker oder /marker)
    - Zeit abfragen (Unix-ns) zur Offset-Messung
    """

    def __init__(self, endpoint: NeonEndpoint, device_id_hint: str = "") -> None:
        self.endpoint = endpoint
        self.device_id_hint = device_id_hint or endpoint.host
        self._recording = False

    # ---- HTTP helpers -------------------------------------------------
    def _post_json(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            url=f"{self.endpoint.base()}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raise NeonError(f"HTTP {e.code} {path}") from e
        except Exception as e:  # pragma: no cover - best effort
            raise NeonError(f"POST failed {path}: {e}") from e

    def _get_json(self, path: str) -> dict:
        try:
            with urllib.request.urlopen(f"{self.endpoint.base()}{path}", timeout=1.5) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raise NeonError(f"HTTP {e.code} {path}") from e
        except Exception as e:  # pragma: no cover - best effort
            raise NeonError(f"GET failed {path}: {e}") from e

    # ---- Recording API ------------------------------------------------
    async def recording_start(self, *, label: str | None = None) -> None:
        self._post_json("/recording:start", {"label": label or ""})
        self._recording = True

    async def recording_begin(self) -> None:
        # Alias für API-Varianten
        await self.recording_start()

    async def recording_stop(self) -> None:
        self._post_json("/recording:stop", {})
        self._recording = False

    async def is_recording(self) -> bool:
        try:
            status = self._get_json("/recording:status")
            return bool(status.get("active", self._recording))
        except NeonError:
            return self._recording

    # ---- Marker API ---------------------------------------------------
    def send_marker(self, name: str, t_host_ns: int | None = None, kv: dict | None = None) -> None:
        payload = {"name": name, "ts_unix_ns": t_host_ns, "kv": kv or {}}
        try:
            self._post_json("/marker", payload)
        except NeonError:
            # tolerant weiterlaufen
            pass

    # ---- Time API -----------------------------------------------------
    def unix_time_ns(self) -> int:
        # Wenn das Gerät eine Zeit-API hat, diese verwenden – sonst Host-Zeit zurückgeben.
        try:
            info = self._get_json("/time")
            val = int(info.get("unix_time_ns", 0))
            return val if val > 0 else int(time.time() * 1e9)
        except NeonError:
            return int(time.time() * 1e9)

    @property
    def device_id(self) -> str:
        return self.device_id_hint
