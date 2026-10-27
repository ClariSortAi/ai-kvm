"""One owner, bounded serial transactions, no automatic input retries."""
from __future__ import annotations

import json
import threading
import time

import serial


class DeviceError(RuntimeError):
    pass


class Device:
    def __init__(self, port: str, serial_factory=serial.Serial):
        self.port = port
        self._serial_factory = serial_factory
        self.serial = None
        self.info: dict = {}
        self.seq = 0
        self.armed = False
        self.fault: str | None = None
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self._quit = threading.Event()
        self._thread = None
        self._stop_generation = 0
        self._last_ack = None

    def _exchange(self, payload: dict) -> dict:
        # Caller holds the lock. An unread/missing response invalidates ownership.
        assert self.serial is not None
        try:
            self.serial.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode() + b"\n")
            line = self.serial.readline(1024)
            if not line.endswith(b"\n"):
                raise DeviceError("Acknowledgment missing: input outcome unknown; inspect target. No retry sent.")
            result = json.loads(line)
            if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                raise DeviceError("Invalid device response")
            if "seq" in payload and result.get("seq") != payload["seq"]:
                raise DeviceError("Response sequence mismatch; input outcome unknown")
            if not result["ok"]:
                raise DeviceError(f"Device rejected request: {result.get('error')}")
            self._last_ack = time.monotonic()
            return result
        except (OSError, ValueError, DeviceError) as exc:
            self.armed = False
            self.cancel.set()
            self.fault = str(exc)
            # Close the transport. Do not send more commands into an ambiguous stream.
            self._quit.set()
            self.serial.close()
            self.serial = None
            raise DeviceError(str(exc)) from exc

    def connect(self) -> dict:
        with self.lock:
            if self.serial is not None:
                return self.info
            if self.fault:
                raise DeviceError(self.fault + "; close and reopen the controller to reconcile")
            self.serial = self._serial_factory(self.port, baudrate=115200, timeout=1.5, write_timeout=1)
            self.serial.reset_input_buffer()
            self.info = self._exchange({"v": 1, "op": "hello"})
            if self.info.get("protocol") != 1 or not self.info.get("session"):
                self.close()
                raise DeviceError("Unsupported firmware protocol")
            self.seq = 0
            self._quit.clear()
            self._thread = threading.Thread(target=self._heartbeat, daemon=True)
            self._thread.start()
            return self.info

    def _request(self, op: str, **args) -> dict:
        with self.lock:
            if self.serial is None:
                raise DeviceError(self.fault or "Device disconnected")
            self.seq += 1
            return self._exchange({"v": 1, "session": self.info["session"], "seq": self.seq, "op": op, **args})

    def arm(self) -> dict:
        generation = self._stop_generation
        with self.lock:
            self.connect()
            if generation != self._stop_generation:
                raise DeviceError("Arm cancelled by STOP while connecting")
            result = self._request("arm")
            if generation != self._stop_generation:
                self.stop()
                raise DeviceError("Arm cancelled by STOP")
            self.armed = True
            self.cancel.clear()
            return result

    def send(self, op: str, **args) -> dict:
        with self.lock:
            if not self.armed or self.cancel.is_set():
                raise DeviceError("Input is disarmed. Arm locally before testing.")
            return self._request(op, **args)

    def type_text(self, text: str) -> dict:
        if not 1 <= len(text) <= 80 or any(ord(c) > 126 or (ord(c) < 32 and c not in "\n\t") for c in text):
            raise ValueError("Use 1..80 US ASCII characters; newline and tab are supported")
        count = 0
        try:
            for char in text:
                self.send("type", text=char)
                count += 1
                # Give STOP and the independent heartbeat a turn between characters.
                if self.cancel.wait(0.005):
                    raise DeviceError("Typing cancelled")
        except DeviceError as exc:
            raise DeviceError(f"{exc}; {count} characters acknowledged, inspect for partial input") from exc
        return {"ok": True, "state": "hid_submitted", "characters_acknowledged": count}

    def stop(self) -> dict:
        self._stop_generation += 1
        self.cancel.set()  # Set before waiting on an in-flight bounded transaction.
        self.armed = False
        with self.lock:
            if self.serial is None:
                return {"ok": False, "release_acknowledged": False, "detail": self.fault or "disconnected; lease must expire"}
            try:
                self._exchange({"v": 1, "op": "stop"})
                # STOP invalidates the old session. New hello remains disarmed.
                self.info = self._exchange({"v": 1, "op": "hello"})
                self.seq = 0
                return {"ok": True, "release_acknowledged": True, "state": "disarmed", "host_receipt_verified": False}
            except DeviceError as exc:
                return {"ok": False, "release_acknowledged": False, "detail": str(exc)}

    def _heartbeat(self):
        while not self._quit.wait(0.25):
            with self.lock:
                if not self.armed or self.serial is None:
                    continue
                try:
                    result = self._exchange({"v": 1, "session": self.info["session"], "op": "ping"})
                    for name in ("hid_ready", "host_protocol"):
                        if name in result:
                            self.info[name] = result[name]
                    if not result.get("armed"):
                        self.armed = False
                        self.cancel.set()
                        self.fault = "Device lease expired or device disarmed; rearm manually"
                except DeviceError:
                    return

    def status(self) -> dict:
        return {"connected": self.serial is not None, "port": self.port, "armed": self.armed,
                "fault": self.fault, "last_ack_age_seconds": time.monotonic()-self._last_ack if self._last_ack else None, "device": self.info}

    def close(self):
        self._quit.set()
        if self.serial is not None:
            self.stop()
            with self.lock:
                if self.serial is not None:
                    self.serial.close()
                    self.serial = None
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

