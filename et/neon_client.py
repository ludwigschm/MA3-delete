from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


class NeonError(RuntimeError):
    ...


@dataclass(slots=True)
class NeonEndpoint:
    host: str
    port: int = 8080

    def base(self) -> str:
        return f"http://{self.host}:{self.port}"


class NeonClient:
    def __init__(self, endpoint: NeonEndpoint, device_id_hint: str = "") -> None:
        self.endpoint = endpoint
        self.device_id_hint = device_id_hint or endpoint.host
        self._recording = False

    def _post_json(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            url=f"{self.endpoint.base()}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")

    def _get_json(self, path: str) -> dict:
        with urllib.request.urlopen(f"{self.endpoint.base()}{path}", timeout=1.5) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")

    async def recording_start(self, *, label: str | None = None) -> None:
        try:
            self._post_json("/recording:start", {"label": label or ""})
            self._recording = True
        except Exception as e:
            raise NeonError(f"recording_start failed: {e}") from e

    async def recording_stop(self) -> None:
        try:
            self._post_json("/recording:stop", {})
            self._recording = False
        except Exception as e:
            raise NeonError(f"recording_stop failed: {e}") from e

    async def is_recording(self) -> bool:
        try:
            status = self._get_json("/recording:status")
            return bool(status.get("active", self._recording))
        except Exception:
            return self._recording

    def send_marker(self, name: str, t_host_ns: int | None = None, kv: dict | None = None) -> None:
        payload = {"name": name, "ts_unix_ns": t_host_ns, "kv": kv or {}}
        try:
            self._post_json("/marker", payload)
        except Exception:
            pass  # tolerant

    def unix_time_ns(self) -> int:
        try:
            info = self._get_json("/time")
            val = int(info.get("unix_time_ns", 0))
            return val if val > 0 else time.time_ns()
        except Exception:
            return time.time_ns()

    @property
    def device_id(self) -> str:
        return self.device_id_hint
