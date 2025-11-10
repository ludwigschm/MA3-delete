from __future__ import annotations
import asyncio, json, time
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Optional
import websockets
from websockets.client import connect
from .config import WS_CANDIDATE_PATHS, WS_CONNECT_TIMEOUT_S
from .neon_client import NeonEndpoint

@dataclass(slots=True)
class NeonWSConfig:
    endpoint: NeonEndpoint
    path: Optional[str] = None  # wenn gesetzt, nur diesen Pfad probieren

def _extract_float(d: dict, keys: tuple[str,...], default=None):
    for k in keys:
        if k in d:
            try: return float(d[k])
            except Exception: pass
    return default

def _extract_int(d: dict, keys: tuple[str,...], default=None):
    for k in keys:
        if k in d:
            try: return int(d[k])
            except Exception: pass
    return default

def _parse_gaze(msg: dict) -> tuple[float,float,Optional[float],Optional[int]]:
    """
    Versucht verschiedene Key-Namen:
    x/y | norm_pos{x,y} | gaze{x,y}; ts: device_time_ns | timestamp_unix_ns | t | ts
    confidence: confidence | conf | validity
    """
    x = _extract_float(msg, ("x","gx","gaze_x"), None)
    y = _extract_float(msg, ("y","gy","gaze_y"), None)
    if x is None or y is None:
        norm = msg.get("norm_pos") or msg.get("norm") or {}
        x = _extract_float(norm, ("x",), x)
        y = _extract_float(norm, ("y",), y)
    conf = _extract_float(msg, ("confidence","conf","validity"), None)
    ts = _extract_int(msg, ("device_time_ns","timestamp_unix_ns","t","ts"), None)
    return x, y, conf, ts

async def _connect_first(ws_urls: list[str], headers: Optional[dict]=None):
    last_exc = None
    for url in ws_urls:
        try:
            return await asyncio.wait_for(connect(url, extra_headers=headers), timeout=WS_CONNECT_TIMEOUT_S)
        except Exception as e:
            last_exc = e
            await asyncio.sleep(0.2)
    raise last_exc or RuntimeError("No WS URL reachable")

async def neon_gaze_stream(cfg: NeonWSConfig) -> AsyncIterator[dict]:
    """
    Liefert rohe Gaze-Objekte (dict) von Neon über WebSocket.
    Erwartet, dass der Stream bereits Gaze-Daten sendet (keine separate Subscribe-Nachricht nötig).
    """
    scheme = "ws"
    base = f"{scheme}://{cfg.endpoint.host}:{cfg.endpoint.port}"
    paths = (cfg.path,) if cfg.path else WS_CANDIDATE_PATHS
    urls = [f"{base}{p}" for p in paths]
    backoff = 0.5
    while True:
        try:
            async with await _connect_first(urls) as ws:
                backoff = 0.5
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        # Einige Implementationen senden {"topic":"gaze","data":{...}}
                        if isinstance(msg, dict) and "data" in msg and isinstance(msg["data"], dict):
                            yield msg["data"]
                        elif isinstance(msg, dict):
                            yield msg
                    except Exception:
                        # parsing error -> weiter
                        continue
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 5.0)
