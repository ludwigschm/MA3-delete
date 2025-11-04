from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(slots=True)
class GazeSample:
    player: str
    x: float
    y: float
    conf: float | None
    t_device_ns: int
    t_host_ns: int


class GazeStream:
    """Dummy-Stream (Platzhalter). Ersetzt später durch echtes Neon-API."""

    def __init__(self, player: str, on_sample: Callable[[GazeSample], None]) -> None:
        self.player = player
        self.on_sample = on_sample
        self._t: Optional[threading.Thread] = None
        self._stop = False

    def start(self) -> None:
        if self._t:
            return

        def loop() -> None:
            while not self._stop:
                time.sleep(0.05)  # 20 Hz no-op

        self._t = threading.Thread(target=loop, name=f"GazeStream-{self.player}", daemon=True)
        self._t.start()

    def stop(self) -> None:
        self._stop = True
