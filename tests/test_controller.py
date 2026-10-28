import json
import time
import threading

import pytest
from PIL import Image
from pydantic import TypeAdapter, ValidationError

from aikvm.capture import Capture, Observation
from aikvm.core import Action, Core
from aikvm.device import Device, DeviceError


class SerialFixture:
    """Transport fault fixture, not a simulation of hardware acceptance."""
    def __init__(self, *args, **kwargs):
        self.writes = []
        self.closed = False
        self.drop = None

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.writes.append(json.loads(data))

    def readline(self, limit):
        payload = self.writes[-1]
        if payload["op"] == self.drop:
            return b""
        result = {"ok": True}
        if payload["op"] == "hello":
            result.update(session="fixture", protocol=1, firmware="test-fixture", hid_ready=True)
        elif payload["op"] == "ping":
            result["armed"] = True
        if "seq" in payload:
            result["seq"] = payload["seq"]
        return json.dumps(result).encode()+b"\n"

    def close(self):
        self.closed = True


def make_device():
    transport = SerialFixture()
    return Device("fixture", serial_factory=lambda *a, **kw: transport), transport


def test_no_input_before_arm_and_connect_does_not_arm():
    device, transport = make_device()
    try:
        device.connect()
        with pytest.raises(DeviceError, match="disarmed"):
            device.send("click", button="left")
        assert [p["op"] for p in transport.writes] == ["hello"]
    finally:
        device.close()


def test_missing_ack_does_not_retry_or_reconnect():
    device, transport = make_device()
    device.arm()
    transport.drop = "click"
    with pytest.raises(DeviceError, match="outcome unknown"):
        device.send("click", button="left")
    assert transport.closed and not device.armed
    assert len([p for p in transport.writes if p["op"] == "click"]) == 1
    with pytest.raises(DeviceError):
        device.arm()
    assert len([p for p in transport.writes if p["op"] == "click"]) == 1


def test_stop_cancels_input_and_stays_disarmed():
    device, transport = make_device()
    device.arm()
    result = device.stop()
    assert result["release_acknowledged"] and not result["host_receipt_verified"]
    with pytest.raises(DeviceError, match="disarmed"):
        device.type_text("ignored")
    assert [p["op"] for p in transport.writes] == ["hello", "arm", "stop", "hello"]
    device.close()


def test_partial_text_is_reported_without_retry():
    device, transport = make_device()
    device.arm()
    transport.drop = "type"
    with pytest.raises(DeviceError, match="0 characters acknowledged"):
        device.type_text("abc")
    assert len([p for p in transport.writes if p["op"] == "type"]) == 1


def test_newlines_are_json_data_not_commands():
    device, transport = make_device()
    try:
        device.arm()
        device.type_text("a\nb")
        assert [p["text"] for p in transport.writes if p["op"] == "type"] == ["a", "\n", "b"]
    finally:
        device.close()


@pytest.mark.parametrize("payload", [
    {"op": "shell", "command": "ignored"},
    {"op": "move", "dx": 128, "dy": 0},
    {"op": "move", "dx": True, "dy": 0},
    {"op": "move", "dx": 1.5, "dy": 0},
    {"op": "type", "text": "\x00"},
    {"op": "type", "text": "é"},
    {"op": "type", "text": "x"*81},
    {"op": "press", "keys": ["UNKNOWN"]},
    {"op": "click", "button": "left", "shell": "ignored"},
])
def test_invalid_actions_are_rejected_before_device(payload):
    with pytest.raises(ValidationError):
        TypeAdapter(Action).validate_python(payload)


class CaptureFixture(Capture):
    def __init__(self):
        super().__init__()
        self.geometry = (0, 0, 1920, 1080, 1)

    def grab(self, crop=None, after=0):
        image = Image.new("RGB", (crop[2], crop[3]) if crop else (1920, 1080))
        obs = Observation(str(time.monotonic_ns()), time.time(), time.monotonic(), self.geometry, image, "bench", "desktop", crop)
        self.last = obs
        return obs


def test_crop_maps_back_to_full_screen():
    capture = CaptureFixture()
    obs = capture.grab((960, 540, 960, 540))
    assert capture.resolve_point(obs.id, 959, 539) == (32767, 32767)


def test_changed_geometry_blocks_absolute_input():
    capture = CaptureFixture()
    obs = capture.grab()
    capture.geometry = (0, 0, 1280, 720, 1)
    with pytest.raises(ValueError, match="geometry changed"):
        capture.resolve_point(obs.id, 100, 100)


def test_stale_frame_wrong_target_and_concurrent_action_never_send():
    device, transport = make_device()
    capture = CaptureFixture()
    core = Core(device, capture, "bench")
    obs = capture.grab()
    action = TypeAdapter(Action).validate_python({"op": "click", "button": "left"})
    with pytest.raises(ValueError, match="Wrong target"):
        core.act("other", obs.id, action)
    obs.monotonic -= 6
    with pytest.raises(ValueError, match="stale"):
        core.act("bench", obs.id, action)
    core._action_lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="no input queued"):
            core.act("bench", obs.id, action)
    finally:
        core._action_lock.release()
    assert transport.writes == []


def test_video_failure_does_not_turn_ack_into_success():
    class AckOnlyDevice:
        def send(self, *args, **kwargs):
            return {"ok": True, "state": "hid_submitted"}
    capture = CaptureFixture()
    obs = capture.grab()
    core = Core(AckOnlyDevice(), capture, "bench")
    def disconnected(**kwargs):
        raise TimeoutError("capture disconnected")
    capture.grab = disconnected
    result, image = core.act("bench", obs.id, TypeAdapter(Action).validate_python({"op": "click"}))
    assert result["state"] == "hid_submitted" and result["outcome_verified"] is False
    assert "capture disconnected" in result["observation_error"] and image is None


def test_stop_during_connection_cannot_late_arm():
    device, transport = make_device()
    entered, release = threading.Event(), threading.Event()
    original = transport.readline
    first = True
    failures = []
    def read(limit):
        nonlocal first
        if first:
            first = False
            entered.set()
            assert release.wait(3)
        return original(limit)
    transport.readline = read
    def arm():
        try:
            device.arm()
        except DeviceError as exc:
            failures.append(str(exc))
    armer = threading.Thread(target=arm)
    armer.start()
    assert entered.wait(2)
    stopper = threading.Thread(target=device.stop)
    stopper.start()
    deadline = time.monotonic()+2
    while not device._stop_generation and time.monotonic()<deadline:
        time.sleep(0.005)
    release.set()
    armer.join(3)
    stopper.join(3)
    assert failures and "cancelled" in failures[0]
    assert not device.armed and all(p["op"]!="arm" for p in transport.writes)
    device.close()



def test_status_reports_acknowledged_input_without_claiming_host_outcome():
    device, _ = make_device()
    try:
        device.arm()
        assert device.status()['last_input_ack_age_seconds'] is None
        device.send('press', keys=['TAB'])
        state = device.status()
        assert state['last_input_ack_age_seconds'] >= 0
        assert state['last_round_trip_ms'] >= 0
        assert state['connected'] and state['armed']
    finally:
        device.close()
