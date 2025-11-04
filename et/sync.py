from __future__ import annotations

import asyncio
import statistics
import time
from typing import Awaitable, Callable

from core.time_sync import TimeSyncManager


class NeonTimeSync:
    """
    Adapter um TimeSyncManager mit einer Messfunktion zu versorgen,
    die Geräte- gegen Host-Zeit misst (in Sekunden).
    """

    def __init__(self, device_id: str, measure_fn: Callable[[int, float], Awaitable[list[float]]]):
        self.manager = TimeSyncManager(device_id, measure_fn)

    async def initial(self) -> float:
        return await self.manager.initial_sync()

    async def maybe(self, observed_drift_s: float | None = None) -> float:
        return await self.manager.maybe_resync(observed_drift_s)
