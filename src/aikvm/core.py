from __future__ import annotations

import time
import threading
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from .capture import Capture
from .device import Device

KEYS = {"CTRL", "SHIFT", "ALT", "GUI", "ENTER", "ESC", "TAB", "BACKSPACE", "DELETE", "UP", "DOWN",
        "LEFT", "RIGHT", "HOME", "END", "PAGEUP", "PAGEDOWN", "INSERT", "SPACE", *[f"F{i}" for i in range(1, 13)]}


def valid_key(key: str) -> str:
    if key not in KEYS and not (len(key) == 1 and 32 <= ord(key) <= 126):
        raise ValueError(f"Unknown key {key!r}; use one printable US ASCII character or a documented named key")
    return key


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TypeAction(Input):
    op: Literal["type"]
    text: str = Field(min_length=1, max_length=80)

    @field_validator("text")
    @classmethod
    def ascii_text(cls, text):
        if any(ord(c) > 126 or (ord(c) < 32 and c not in "\n\t") for c in text):
            raise ValueError("US ASCII only; newline and tab allowed")
        return text


class PressAction(Input):
    op: Literal["press"]
    keys: list[str] = Field(min_length=1, max_length=6)

    @field_validator("keys")
    @classmethod
    def supported(cls, keys):
        return [valid_key(key) for key in keys]


class KeyAction(Input):
    op: Literal["key_down", "key_up"]
    key: str

    @field_validator("key")
    @classmethod
    def supported(cls, key):
        return valid_key(key)


class MoveAction(Input):
    op: Literal["move"]
    dx: StrictInt = Field(ge=-127, le=127)
    dy: StrictInt = Field(ge=-127, le=127)


class AbsoluteAction(Input):
    op: Literal["move_abs"]
    x: StrictInt = Field(ge=0)
    y: StrictInt = Field(ge=0)


class ButtonAction(Input):
    op: Literal["click", "button_down", "button_up"]
    button: Literal["left", "right", "middle"] = "left"


class ScrollAction(Input):
    op: Literal["scroll"]
    ticks: StrictInt = Field(ge=-127, le=127)


class ReleaseAction(Input):
    op: Literal["release"]


Action = Annotated[Union[TypeAction, PressAction, KeyAction, MoveAction, AbsoluteAction, ButtonAction,
                         ScrollAction, ReleaseAction], Field(discriminator="op")]


class Core:
    def __init__(self, device: Device, capture: Capture, target: str):
        self.device, self.capture, self.target = device, capture, target
        self._action_lock = threading.Lock()

    def act(self, target_id: str, frame_id: str, action: Action):
        if not self._action_lock.acquire(blocking=False):
            raise RuntimeError("Another action is executing; no input queued")
        try:
            return self._act(target_id, frame_id, action)
        finally:
            self._action_lock.release()

    def _act(self, target_id: str, frame_id: str, action: Action):
        if target_id != self.target:
            raise ValueError("Wrong target binding")
        prior = self.capture.last
        if not prior or prior.id != frame_id or time.monotonic()-prior.monotonic > 5:
            raise ValueError("Observation missing or stale; observe again")
        payload = action.model_dump()
        op = payload.pop("op")
        if op == "move_abs":
            payload["x"], payload["y"] = self.capture.resolve_point(frame_id, payload["x"], payload["y"])
        if op == "type":
            result = self.device.type_text(payload["text"])
        else:
            result = self.device.send(op, **payload)
        finished = time.monotonic()
        time.sleep(0.1)
        try:
            observation = self.capture.grab(after=finished)
            result["observation"] = observation.metadata()
            result["outcome_verified"] = False
            return result, observation
        except (TimeoutError, OSError, ValueError) as exc:
            return {**result, "observation_error": str(exc), "outcome_verified": False}, None

    def close(self):
        self.device.close()
        self.capture.close()

