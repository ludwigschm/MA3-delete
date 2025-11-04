from __future__ import annotations

from typing import Awaitable, Callable


# Platzhalter, wenn du core/time_sync nutzt, kannst du hier adaptieren.
class NeonTimeSync:
    def __init__(self, device_id: str, measure_fn: Callable[[int, float], Awaitable[list[float]]]):
        self.device_id = device_id
        self.measure_fn = measure_fn

    async def initial(self) -> float:
        vals = await self.measure_fn(5, 0.5)
        return sum(vals) / len(vals) if vals else 0.0

    async def maybe(self, observed_drift_s: float | None = None) -> float:
        vals = await self.measure_fn(3, 0.5)
        return sum(vals) / len(vals) if vals else 0.0
