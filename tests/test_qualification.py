import pytest

from aikvm.qualification import diagnostic_key
from aikvm.device import DeviceError


class DiagnosticDevice:
    def __init__(self):
        self.info = {"usb_profile": "bios", "hid_ready": True}
        self.calls = []
        self.error = None

    def send(self, op, **kwargs):
        self.calls.append((op, kwargs))
        if self.error:
            raise self.error
        return {"ok": True, "state": "hid_submitted"}


def test_diagnostic_key_requires_physical_observer_and_navigation_key():
    device = DiagnosticDevice()
    for key, watching in [("DOWN", False), ("ENTER", True), ("F10", True)]:
        with pytest.raises(ValueError):
            diagnostic_key(device, key, watching)
    assert device.calls == []


@pytest.mark.parametrize("info", [{"usb_profile": "desktop", "hid_ready": True},
                                  {"usb_profile": "bios", "hid_ready": False}])
def test_diagnostic_rejects_wrong_profile_or_missing_usb(info):
    device = DiagnosticDevice()
    device.info = info
    with pytest.raises(ValueError):
        diagnostic_key(device, "DOWN", True)
    assert device.calls == []


def test_diagnostic_sends_one_key_without_claiming_observed_outcome():
    device = DiagnosticDevice()
    result = diagnostic_key(device, "DOWN", True)
    assert device.calls == [("press", {"keys": ["DOWN"]})]
    assert not result["host_outcome_verified"]
    assert not result["video_verified"]
    assert not result["qualification_evidence"]
    assert "passed" not in result


@pytest.mark.parametrize("error", ["Input is disarmed", "Acknowledgment missing: outcome unknown"])
def test_diagnostic_propagates_device_failure_without_retry(error):
    device = DiagnosticDevice()
    device.error = DeviceError(error)
    with pytest.raises(DeviceError, match=error):
        diagnostic_key(device, "DOWN", True)
    assert len(device.calls) == 1
