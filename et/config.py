from __future__ import annotations

import os
from dataclasses import dataclass

from .neon_client import NeonEndpoint


@dataclass(slots=True)
class ETConfig:
    p1: NeonEndpoint | None
    p2: NeonEndpoint | None


def load_from_env() -> ETConfig:
    def parse(name: str) -> NeonEndpoint | None:
        val = os.getenv(name, "")
        if not val:
            return None
        if ":" in val:
            host, port = val.split(":", 1)
            return NeonEndpoint(host.strip(), int(port))
        return NeonEndpoint(val.strip(), 8080)

    return ETConfig(parse("NEON_P1"), parse("NEON_P2"))


WS_CANDIDATE_PATHS = (
    "/ws/gaze",  # bevorzugt
    "/ws",  # fallback
    "/realtime",  # fallback
)
WS_CONNECT_TIMEOUT_S = float(os.getenv("NEON_WS_TIMEOUT_S", "3.0"))
