from __future__ import annotations
import asyncio, time
from dataclasses import dataclass
from typing import Callable, Optional
from .neon_ws import NeonWSConfig, neon_gaze_stream
from .neon_client import NeonEndpoint

@dataclass(slots=True)
class GazeSample:
    player: str
    x: float
    y: float
    conf: float | None
    t_device_ns: int
    t_host_ns: int

class GazeStream:
    def __init__(self, player: str, endpoint: NeonEndpoint, on_sample: Callable[[GazeSample], None]) -> None:
        self.player = player
        self.endpoint = endpoint
        self.on_sample = on_sample
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run(), name=f"GazeStream-{self.player}")

    async def _run(self) -> None:
        cfg = NeonWSConfig(self.endpoint)
        async for msg in neon_gaze_stream(cfg):
            t_host_ns = time.time_ns()
            # tolerant parsers:
            x = msg.get("x") or msg.get("gx") or (msg.get("norm_pos") or {}).get("x")
            y = msg.get("y") or msg.get("gy") or (msg.get("norm_pos") or {}).get("y")
            if x is None or y is None:
                continue
            try:
                x = float(x); y = float(y)
            except Exception:
                continue
            conf = msg.get("confidence", msg.get("conf", msg.get("validity", None)))
            try:
                conf = None if conf is None else float(conf)
            except Exception:
                conf = None
            t_dev = msg.get("device_time_ns", msg.get("timestamp_unix_ns", None))
            try:
                t_dev = int(t_dev) if t_dev is not None else t_host_ns
            except Exception:
                t_dev = t_host_ns
            self.on_sample(GazeSample(self.player, x, y, conf, t_dev, t_host_ns))

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
