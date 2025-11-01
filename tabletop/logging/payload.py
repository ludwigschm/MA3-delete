from __future__ import annotations

from typing import Any, Callable, Dict, Optional


def enrich_payload(
    base: Optional[Dict[str, Any]],
    *,
    player: Optional[int],
    phase_obj: Any,
    round_index: int,
    actor_label_fn: Callable[[Optional[int]], str],
    player_roles: Dict[int, Any],
) -> Dict[str, Any]:
    """Merge experiment metadata into event payloads."""

    payload: Dict[str, Any] = dict(base or {})
    phase_name = getattr(phase_obj, "name", None)
    payload.setdefault("phase", phase_name if phase_name else str(phase_obj))
    payload.setdefault("round_idx", max(0, (round_index or 1) - 1))
    if player in (1, 2):
        payload.setdefault("game_player", player)
        payload.setdefault("player_role", player_roles.get(player))
        payload.setdefault("actor", actor_label_fn(player))
    else:
        payload.setdefault("actor", "SYS")
    return payload
