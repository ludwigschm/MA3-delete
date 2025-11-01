"""Utilities for mirroring UI events into the marker hub."""

from __future__ import annotations

import logging
from typing import Any, Optional

from tabletop.sync.markers import MarkerHub

log = logging.getLogger(__name__)


class EventBridge:
    """Bridge UI interaction events to the :class:`MarkerHub`."""

    def __init__(self, marker_hub: Optional[MarkerHub]) -> None:
        self._marker_hub = marker_hub

    def enqueue(self, marker_kind: str, payload: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        """Forward an interaction marker to the hub.

        The method returns the event dictionary created by the marker hub so
        that callers can persist the data alongside their regular UI logs.
        """

        if self._marker_hub is None:
            return None
        try:
            return self._marker_hub.emit(marker_kind, payload or {})
        except Exception:  # pragma: no cover - defensive
            log.exception("Failed to enqueue marker %s", marker_kind)
            return None
