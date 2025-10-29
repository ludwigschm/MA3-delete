"""Utilities for managing the fixation overlay sequence and tone playback."""

from __future__ import annotations

import importlib
import importlib.util
import threading
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

import numpy as np
import sounddevice as sd
from kivy.logger import Logger

if TYPE_CHECKING:
    from tabletop.pupil_bridge import PupilBridge


_FIXATION_CROSS_ATTR = "_fixation_cross_overlay"

_GRAPHICS_SPEC = importlib.util.find_spec("kivy.graphics")
if _GRAPHICS_SPEC is not None:
    _graphics = importlib.import_module("kivy.graphics")
    _Color = getattr(_graphics, "Color", None)
    _Line = getattr(_graphics, "Line", None)
else:  # pragma: no cover - executed only when Kivy is unavailable
    _Color = None
    _Line = None


def generate_fixation_tone(
    sample_rate: int = 44100,
    duration: float = 0.2,
    frequency: float = 1000.0,
    amplitude: float = 0.9,
):
    """Create the sine-wave tone that is played during the fixation sequence."""

    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return amplitude * np.sin(2 * np.pi * frequency * t)


def play_fixation_tone(controller: Any) -> None:
    """Play the fixation tone asynchronously using sounddevice."""

    tone = getattr(controller, "fixation_tone", None)
    if tone is None:
        return

    sample_rate = getattr(controller, "fixation_tone_fs", 44100)
    tone_data = tone.copy()

    def _play():
        try:
            sd.play(tone_data, sample_rate)
            sd.wait()
        except Exception as exc:  # pragma: no cover - audio hardware dependent
            print(f"Warnung: Ton konnte nicht abgespielt werden: {exc}")

    threading.Thread(target=_play, daemon=True).start()


def run_fixation_sequence(
    controller: Any,
    *,
    schedule_once: Callable[[Callable[[float], None], float], Any],
    stop_image: Optional[Path | str],
    live_image: Optional[Path | str],
    on_complete: Optional[Callable[[], None]] = None,
    bridge: Optional["PupilBridge"] = None,
    player: Optional[str] = None,
    session: Optional[int] = None,
    block: Optional[int] = None,
) -> None:
    """Execute the fixation sequence using the provided controller state."""

    if getattr(controller, "fixation_running", False):
        Logger.info("Fixation: sequence already active – skipping new start")
        return

    if getattr(controller, "app_stopping", False) or getattr(controller, "screen_leaving", False):
        Logger.info("Fixation: start aborted – controller is stopping")
        return

    overlay = getattr(controller, "fixation_overlay", None)
    image = getattr(controller, "fixation_image", None)
    try:
        _ = overlay.opacity if overlay is not None else None
    except ReferenceError:
        overlay = None
    try:
        _ = image.opacity if image is not None else None
    except ReferenceError:
        image = None

    if overlay is None or image is None:
        if hasattr(controller, "fixation_required"):
            controller.fixation_required = False
        if on_complete:
            on_complete()
        return

    def _send_sync_event(name: str) -> None:
        if bridge is None or player is None:
            return
        if not bridge.is_connected(player):
            return
        if getattr(controller, "app_stopping", False) or getattr(controller, "screen_leaving", False):
            Logger.info(
                "Fixation: skip sync event %s – controller stopping", name
            )
            return
        payload: dict[str, Any] = {}
        if session is not None:
            payload["session"] = session
        if block is not None:
            payload["block"] = block
        payload["player"] = player
        bridge.send_event(name, player, payload)

    controller.fixation_running = True
    controller.pending_fixation_callback = on_complete
    state = _ensure_state(controller, overlay, image)
    state.cancelled = False

    def _register_event(event: Any) -> None:
        if event is not None:
            state.events.append(event)

    def _wrap(callback: Callable[[float], None], description: str) -> Callable[[float], None]:
        def _inner(dt: float) -> None:
            event = getattr(_inner, "event", None)
            if event in state.events:
                with suppress(ValueError):
                    state.events.remove(event)
            if state.cancelled:
                Logger.info("Fixation: skip %s – sequence cancelled", description)
                return
            if getattr(controller, "app_stopping", False) or getattr(controller, "screen_leaving", False):
                Logger.info("Fixation: skip %s – controller stopping", description)
                return
            callback(dt)

        return _inner

    def _schedule(callback: Callable[[float], None], delay: float, description: str) -> Any:
        wrapped = _wrap(callback, description)
        event = schedule_once(wrapped, delay)
        setattr(wrapped, "event", event)
        _register_event(event)
        return event

    def _complete(cancelled: bool = False) -> None:
        if state.cancelled and not cancelled:
            return
        state.cancelled = True

        for event in list(state.events):
            try:
                event.cancel()
            except Exception:
                Logger.debug("Fixation: failed to cancel scheduled event", exc_info=True)
        state.events.clear()

        if widget_is_alive(overlay):
            try:
                if getattr(overlay, "parent", None) is not None:
                    parent = overlay.parent
                    if parent is not None and hasattr(parent, "remove_widget"):
                        parent.remove_widget(overlay)
            except ReferenceError:
                pass
            try:
                overlay.opacity = 0
                overlay.disabled = True
            except ReferenceError:
                pass

        if widget_is_alive(image):
            try:
                image.opacity = 0
            except ReferenceError:
                pass
            try:
                _remove_cross_overlay(image)
            except ReferenceError:
                pass

        controller.fixation_running = False
        if hasattr(controller, "fixation_required"):
            controller.fixation_required = False

        callback = getattr(controller, "pending_fixation_callback", None)
        controller.pending_fixation_callback = None

        updater = getattr(controller, "_maybe_enable_start_buttons", None)
        if callable(updater):
            try:
                updater()
            except Exception:
                Logger.debug("Fixation: failed to refresh start buttons", exc_info=True)

        if not cancelled and callback is not None:
            try:
                callback()
            except Exception:
                Logger.exception("Fixation: on_complete callback failed")

        if state.start_sent and not state.end_sent and not cancelled:
            _send_sync_event("sync.fixation_end")
            state.end_sent = True

        updater = getattr(controller, "_maybe_enable_start_buttons", None)
        if callable(updater):
            try:
                updater()
            except Exception:
                Logger.debug("Fixation: failed to refresh start buttons", exc_info=True)

        controller._fixation_state = None

    def _initialize(_dt: float) -> None:
        if state.cancelled:
            Logger.info("Fixation: initialization skipped – already cancelled")
            return

        try:
            parent = getattr(overlay, "parent", None)
        except ReferenceError:
            Logger.info("Fixation: overlay reference lost during init")
            _complete(cancelled=True)
            return

        if parent is not None and parent is not controller:
            try:
                parent.remove_widget(overlay)
            except Exception:
                Logger.debug("Fixation: failed to detach overlay from previous parent", exc_info=True)

        if getattr(overlay, "parent", None) is not controller:
            try:
                controller.add_widget(overlay)
            except Exception:
                Logger.exception("Fixation: failed to attach overlay to controller")
                _complete(cancelled=True)
                return

        if not widget_is_alive(overlay):
            Logger.info("Fixation: overlay not attached – aborting sequence")
            _complete(cancelled=True)
            return

        try:
            overlay.opacity = 1
            overlay.disabled = False
        except ReferenceError:
            Logger.info("Fixation: overlay destroyed while enabling")
            _complete(cancelled=True)
            return

        for attr in ("btn_start_p1", "btn_start_p2"):
            btn = getattr(controller, attr, None)
            if btn is not None and hasattr(btn, "set_live"):
                try:
                    btn.set_live(False)
                except ReferenceError:
                    Logger.debug("Fixation: start button reference lost", exc_info=True)

        if widget_is_alive(image):
            try:
                image.opacity = 1
            except ReferenceError:
                Logger.debug("Fixation: image lost while enabling", exc_info=True)
            try:
                _set_image_source(image, live_image, fallback="cross")
            except ReferenceError:
                Logger.debug("Fixation: image lost while setting source", exc_info=True)

        _send_sync_event("sync.fixation_start")
        state.start_sent = True
        Logger.info("Fixation: sequence initialized")

    def finish(_dt: float) -> None:
        Logger.info("Fixation: finishing sequence")
        _complete(cancelled=False)

    def show_final_live(_dt: float) -> None:
        if widget_is_alive(image):
            try:
                _set_image_source(image, live_image, fallback="cross")
            except ReferenceError:
                Logger.debug("Fixation: image lost while restoring live view", exc_info=True)
        else:
            Logger.info("Fixation: image not available for final live view")
        _schedule(finish, 5, "finish")

    def show_stop_and_tone(_dt: float) -> None:
        if widget_is_alive(image):
            try:
                _set_image_source(image, stop_image, fallback="blank")
            except ReferenceError:
                Logger.debug("Fixation: image lost while showing stop image", exc_info=True)
        else:
            Logger.info("Fixation: image not available for stop frame")
        try:
            play_fixation_tone(controller)
        except Exception:
            Logger.exception("Fixation: failed to play tone")
        _send_sync_event("sync.flash_beep")
        _schedule(show_final_live, 0.2, "show_final_live")

    Logger.info("Fixation: scheduling initialization")
    _schedule(_initialize, 0.0, "initialize")
    _schedule(show_stop_and_tone, 5, "show_stop_and_tone")


def _path_to_source(image_path: Optional[Path | str]) -> str:
    if image_path is None:
        return ""
    if isinstance(image_path, Path):
        candidate = image_path
    else:
        candidate = Path(image_path)
    return str(candidate) if candidate.exists() else ""


def _set_image_source(image: Any, image_path: Optional[Path | str], *, fallback: str) -> None:
    source = _path_to_source(image_path)
    if source:
        image.source = source
        _remove_cross_overlay(image)
        return

    image.source = ""
    if fallback == "cross":
        _ensure_cross_overlay(image)
    else:
        _remove_cross_overlay(image)


def _ensure_cross_overlay(image: Any) -> None:
    if _Color is None or _Line is None:
        return
    if getattr(image, _FIXATION_CROSS_ATTR, None) is None:
        with image.canvas.after:
            color = _Color(1, 1, 1, 1)
            line1 = _Line(points=[], width=2, cap="square")
            line2 = _Line(points=[], width=2, cap="square")
        image.bind(size=_update_cross_overlay, pos=_update_cross_overlay)
        setattr(image, _FIXATION_CROSS_ATTR, (color, line1, line2))
    _update_cross_overlay(image)


def _remove_cross_overlay(image: Any) -> None:
    cross = getattr(image, _FIXATION_CROSS_ATTR, None)
    if not cross:
        return
    image.unbind(size=_update_cross_overlay, pos=_update_cross_overlay)
    color, line1, line2 = cross
    canvas = image.canvas.after
    for instruction in (line2, line1, color):
        if instruction in canvas.children:
            canvas.remove(instruction)
    delattr(image, _FIXATION_CROSS_ATTR)


def _update_cross_overlay(image: Any, *_: Any) -> None:
    cross = getattr(image, _FIXATION_CROSS_ATTR, None)
    if not cross:
        return
    _, line1, line2 = cross
    width, height = image.size
    if width <= 0 or height <= 0:
        line1.points = []
        line2.points = []
        return

    margin = min(width, height) * 0.2
    x1 = image.x + margin
    x2 = image.x + width - margin
    y1 = image.y + margin
    y2 = image.y + height - margin
    line1.points = [x1, y1, x2, y2]
    line2.points = [x1, y2, x2, y1]
    stroke = max(min(width, height) * 0.05, 2.0)
    line1.width = stroke
    line2.width = stroke


__all__ = [
    "generate_fixation_tone",
    "play_fixation_tone",
    "run_fixation_sequence",
    "cancel_fixation_sequence",
    "widget_is_alive",
]
@dataclass
class _FixationSequenceState:
    overlay: Any
    image: Any
    events: list[Any] = field(default_factory=list)
    cancelled: bool = False
    start_sent: bool = False
    end_sent: bool = False


def widget_is_alive(widget: Any) -> bool:
    """Return ``True`` if the widget reference is still valid and attached."""

    try:
        if widget is None:
            return False
        parent = widget.parent
        root = widget.get_root_window()
        return parent is not None and root is not None
    except ReferenceError:
        return False


def _ensure_state(controller: Any, overlay: Any, image: Any) -> _FixationSequenceState:
    state = getattr(controller, "_fixation_state", None)
    if state is not None and isinstance(state, _FixationSequenceState):
        return state
    state = _FixationSequenceState(overlay=overlay, image=image)
    controller._fixation_state = state  # hold strong references
    return state


def cancel_fixation_sequence(controller: Any, *, reason: str | None = None) -> None:
    """Cancel a running fixation sequence safely."""

    state = getattr(controller, "_fixation_state", None)
    if not isinstance(state, _FixationSequenceState):
        controller.fixation_running = False
        controller.pending_fixation_callback = None
        return

    if state.cancelled:
        return

    state.cancelled = True

    if reason:
        Logger.info("Fixation: cancelling sequence (%s)", reason)

    for event in list(state.events):
        try:
            event.cancel()
        except Exception:
            Logger.debug("Fixation: failed to cancel scheduled event", exc_info=True)
    state.events.clear()

    overlay = state.overlay
    image = state.image

    if widget_is_alive(overlay):
        try:
            if getattr(overlay, "parent", None) is not None:
                parent = overlay.parent
                if parent is not None and hasattr(parent, "remove_widget"):
                    parent.remove_widget(overlay)
        except ReferenceError:
            pass
        try:
            overlay.opacity = 0
            overlay.disabled = True
        except ReferenceError:
            pass

    if widget_is_alive(image):
        try:
            _remove_cross_overlay(image)
        except ReferenceError:
            pass

    controller.fixation_running = False
    if hasattr(controller, "fixation_required"):
        controller.fixation_required = False

    controller.pending_fixation_callback = None
    updater = getattr(controller, "_maybe_enable_start_buttons", None)
    if callable(updater):
        try:
            updater()
        except Exception:
            Logger.debug("Fixation: failed to refresh start buttons", exc_info=True)
    controller._fixation_state = None
