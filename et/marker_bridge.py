from __future__ import annotations

import time
from typing import Any, Optional

from .neon_client import NeonClient


class ETMarkerBridge:
    """
    Spiegelt relevante UI-Events als Neon-Marker.
    - fix.* und sync.* werden ohne Host-Zeit gesendet (Gerät stempelt)
    - andere Events optional mit Host-Spiegel t_host_ns
    """

    def __init__(self, client_p1: Optional[NeonClient], client_p2: Optional[NeonClient]):
        self.p1 = client_p1
        self.p2 = client_p2

    def _for_player(self, player: int | str) -> Optional[NeonClient]:
        key = str(player).lower()
        if key in ("1", "p1"):
            return self.p1
        if key in ("2", "p2"):
            return self.p2
        return None

    def handle_ui_event(self, event: dict[str, Any]) -> None:
        action = event.get("action", "")
        player = event.get("payload", {}).get("player") or event.get("payload", {}).get("game_player")
        for_players = event.get("payload", {}).get("players")  # Fixation könnte mehrere betreffen
        targets = [player] if player else (for_players or [])
        targets = targets or ["p1", "p2"]

        # Kritische Marker direkt ohne Host-Zeit
        if action.startswith("fix.") or action.startswith("sync."):
            for t in targets:
                cli = self._for_player(t)
                if cli:
                    cli.send_marker(action)
            return

        # Sonstige Events inkl. Host-Spiegel
        t_host_ns = time.time_ns()
        for t in targets:
            cli = self._for_player(t)
            if cli:
                cli.send_marker(action, t_host_ns=t_host_ns)
