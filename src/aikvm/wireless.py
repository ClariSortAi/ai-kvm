"""TLS-PSK listener for the paired board's outbound connection. Python 3.13+."""
from __future__ import annotations

import base64
import ipaddress
import json
import secrets
import socket
import ssl
import time
import threading
from pathlib import Path

from .device import Device, DeviceError

CIPHER = "PSK-AES128-GCM-SHA256"


def server_context(identity: str, key: bytes) -> ssl.SSLContext:
    if not getattr(ssl, "HAS_PSK", False):
        raise RuntimeError("Wireless control requires Python 3.13+ with TLS-PSK support; use the prepared .venv")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers(CIPHER)
    context.set_psk_server_callback(lambda presented: key if secrets.compare_digest(presented or "", identity) else b"")
    return context


class SocketStream:
    def __init__(self, connection: ssl.SSLSocket):
        self.connection = connection
        self.connection.settimeout(1.5)
        self.buffer = bytearray()

    def reset_input_buffer(self):
        # The device sends no unsolicited data; do not discard a response.
        pass

    def write(self, data: bytes):
        self.connection.sendall(data)
        return len(data)

    def readline(self, limit: int):
        while b"\n" not in self.buffer and len(self.buffer) < limit:
            data = self.connection.recv(min(4096, limit-len(self.buffer)))
            if not data:
                break
            self.buffer.extend(data)
        end = self.buffer.find(b"\n")
        size = end+1 if end >= 0 else len(self.buffer)
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def close(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.connection.close()


def save_pairing(path: Path, info: dict, key: bytes):
    import win32crypt
    protected = win32crypt.CryptProtectData(key, "AI KVM TLS pairing", None, None, None, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = {**info, "key_dpapi": base64.b64encode(protected).decode(), "key_storage": "windows_current_user_dpapi"}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(output, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_pairing(path: str | Path) -> tuple[dict, bytes]:
    import win32crypt
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    key = win32crypt.CryptUnprotectData(base64.b64decode(data["key_dpapi"]), None, None, None, 0)[1]
    if len(key) != 32 or data["identity"] != "aikvm-"+data["device_id"]:
        raise ValueError("Invalid pairing file")
    ipaddress.IPv4Address(data["controller_ip"])
    if not 1024 <= data["port"] <= 65535:
        raise ValueError("Invalid pairing port")
    return data, key


class WirelessDevice(Device):
    def __init__(self, pairing: str | Path, wait_seconds=30):
        self.pairing, self._key = load_pairing(pairing)
        self.wait_seconds = wait_seconds
        self.listener = None
        self._cancel_wait = threading.Event()
        super().__init__(f"tls:{self.pairing['controller_ip']}:{self.pairing['port']}", serial_factory=self._accept)

    def _accept(self, *args, **kwargs):
        self._cancel_wait.clear()
        context = server_context(self.pairing["identity"], self._key)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind((self.pairing["controller_ip"], self.pairing["port"]))
            listener.listen(1)
            listener.settimeout(0.5)
            self.listener = listener
            deadline = time.monotonic()+self.wait_seconds
            while time.monotonic() < deadline and not self._cancel_wait.is_set():
                try:
                    connection, _peer = listener.accept()
                except socket.timeout:
                    continue
                connection.settimeout(2)
                try:
                    secure = context.wrap_socket(connection, server_side=True)
                except (OSError, ssl.SSLError):
                    connection.close()
                    continue  # Wrong/unknown keys get no application command path.
                if secure.cipher()[0] != CIPHER:
                    secure.close()
                    continue
                secure.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                return SocketStream(secure)
            raise DeviceError("Paired board did not connect. Check power, 2.4GHz Wi-Fi, controller IP and Private-network firewall rule.")
        finally:
            listener.close()
            self.listener = None

    def cancel_wait(self):
        self._cancel_wait.set()
        if self.listener:
            self.listener.close()

    def connect(self):
        info = super().connect()
        if info.get("device_id") != self.pairing["device_id"] or info.get("transport") != "tls-psk":
            self.close()
            raise DeviceError("Paired device identity or authenticated transport mismatch")
        return info

    def status(self):
        return {**super().status(), "transport": "tls-psk", "paired_device_id": self.pairing["device_id"]}


def provision(device: Device, pairing_path: Path, controller_ip: str, port: int, ssid: str, password: str):
    ipaddress.IPv4Address(controller_ip)
    if not 1024 <= port <= 65535 or not 1 <= len(ssid.encode()) <= 32 or not 8 <= len(password.encode()) <= 63:
        raise ValueError("Use a valid port, 1..32-byte SSID and 8..63-byte WPA password")
    info = device.connect()
    if info.get("transport") != "usb-cdc" or device.armed:
        raise ValueError("Provisioning requires disarmed physical USB")
    if pairing_path.exists():
        previous, key = load_pairing(pairing_path)
        if previous["device_id"] != info["device_id"]:
            raise ValueError("Pairing file belongs to a different device; choose a new path")
    else:
        key = secrets.token_bytes(32)
    pairing = {"device_id": info["device_id"], "identity": "aikvm-"+info["device_id"],
               "controller_ip": controller_ip, "port": port, "state": "provisioning_pending"}
    # Preserve the canonical key even if the USB acknowledgment is lost.
    save_pairing(pairing_path, pairing, key)
    with device.lock:
        result = device._exchange({"v": 1, "op": "provision", "ssid": ssid, "password": password,
                                   "host": controller_ip, "port": port, "identity": pairing["identity"], "psk": key.hex()})
    save_pairing(pairing_path, {**pairing, "state": "provisioned"}, key)
    return {"state": result["state"], "device_id": info["device_id"], "pairing_file": str(pairing_path),
            "controller_ip": controller_ip, "port": port}
