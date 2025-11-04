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

    return ETConfig(p1=parse("NEON_P1"), p2=parse("NEON_P2"))
