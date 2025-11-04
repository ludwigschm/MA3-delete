from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional
import threading
import time


@dataclass(slots=True)
class GazeSample:
    player: str     # "p1"/"p2"
    x: float        # normalized 0..1
    y: float
    conf: float | None
    t_device_ns: int
    t_host_ns: int


class GazeStream:
    """
    Platzhalter-Stream:
    - bremst nicht, läuft no-op wenn kein SDK vorhanden
    - Callback wird mit GazeSample aufgerufen
    """

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
                # hier später SDK-Integration (Neon fused gaze)
                time.sleep(0.05)

        self._t = threading.Thread(target=loop, name=f"GazeStream-{self.player}", daemon=True)
        self._t.start()

    def stop(self) -> None:
        self._stop = True
