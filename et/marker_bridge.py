from __future__ import annotations

import time
from typing import Any, Optional

from .neon_client import NeonClient


class ETMarkerBridge:
    """
    Spiegelt UI-Events als Neon-Marker.
    - 'fix.*'/'sync.*' ohne Hostzeit (Gerät stempelt)
    - andere mit Hostzeit-Spiegel
    """

    def __init__(self, client_p1: Optional[NeonClient], client_p2: Optional[NeonClient]):
        self.p1 = client_p1
        self.p2 = client_p2

    def _for(self, key: str) -> Optional[NeonClient]:
        k = key.lower()
        if k in ("1", "p1"):
            return self.p1
        if k in ("2", "p2"):
            return self.p2
        return None

    def handle_ui_event(self, event: dict) -> None:
        action = event.get("action", "")
        payload = event.get("payload") or {}
        targets = payload.get("players") or [payload.get("player")] if payload.get("player") else []
        if not targets:
            targets = ["p1", "p2"]  # default beide

        if action.startswith(("fix.", "sync.")):
            for t in targets:
                cli = self._for(str(t))
                if cli:
                    cli.send_marker(action)
            return

        t_host = time.time_ns()
        for t in targets:
            cli = self._for(str(t))
            if cli:
                cli.send_marker(action, t_host_ns=t_host)
