from __future__ import annotations
import time, statistics, asyncio
from typing import Callable, Awaitable
from .neon_client import NeonClient

class NeonTimeSync:
    def __init__(self, client: NeonClient):
        self.client = client

    async def _measure_once(self) -> float:
        # host t1
        t1 = time.time_ns()
        d1 = self.client.unix_time_ns()
        t2 = time.time_ns()
        # zweite Messung für bessere Mitte
        t3 = time.time_ns()
        d2 = self.client.unix_time_ns()
        t4 = time.time_ns()
        # host midpoints
        h1 = (t1 + t2) // 2
        h2 = (t3 + t4) // 2
        o1 = (d1 - h1) / 1e9
        o2 = (d2 - h2) / 1e9
        return (o1 + o2) / 2.0

    async def sample_offsets(self, n: int = 7, delay_s: float = 0.05) -> list[float]:
        vals = []
        for _ in range(max(1, n)):
            try:
                vals.append(await self._measure_once())
            except Exception:
                pass
            await asyncio.sleep(delay_s)
        return vals

    async def initial(self) -> float:
        vals = await self.sample_offsets( nine := 9, 0.03)
        return statistics.median(vals) if vals else 0.0

    async def maybe(self, observed_drift_s: float | None = None) -> float:
        vals = await self.sample_offsets(5, 0.04)
        return statistics.median(vals) if vals else 0.0
