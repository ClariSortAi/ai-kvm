import json
import secrets
import socket
import ssl
import threading
import time

import pytest

from aikvm.wireless import WirelessDevice, load_pairing, save_pairing, server_context, CIPHER, provision
from test_controller import make_device


def client_context(identity, key):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # PSK authenticates the peer; no certificates are used.
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers(CIPHER)
    context.set_psk_client_callback(lambda hint: (identity, key))
    return context


def test_pairing_is_dpapi_protected_and_bound_to_device(tmp_path):
    path = tmp_path/"pairing.json"
    key = secrets.token_bytes(32)
    info = {"device_id": "123456789abc", "identity": "aikvm-123456789abc", "controller_ip": "127.0.0.1", "port": 8787}
    save_pairing(path, info, key)
    loaded, recovered = load_pairing(path)
    assert recovered == key
    assert key.hex() not in path.read_text() and "key_dpapi" in loaded
    assert loaded["device_id"] == info["device_id"]


@pytest.mark.parametrize("identity,wrong_key", [("unknown", False), ("aikvm-test", True)])
def test_tls_rejects_unknown_identity_and_wrong_key(identity, wrong_key):
    key = secrets.token_bytes(32)
    listener = socket.socket()
    listener.bind(("127.0.0.1",0))
    listener.listen(1)
    errors = []
    def server():
        connection, _ = listener.accept()
        connection.settimeout(2)
        try:
            server_context("aikvm-test", key).wrap_socket(connection,server_side=True)
        except (OSError, ssl.SSLError):
            errors.append("rejected_before_application_input")
        finally:
            connection.close()
    thread = threading.Thread(target=server)
    thread.start()
    try:
        context = client_context(identity, secrets.token_bytes(32) if wrong_key else key)
        with pytest.raises((ssl.SSLError, OSError)):
            with socket.create_connection(listener.getsockname(),timeout=2) as raw:
                context.wrap_socket(raw,server_hostname=None)
        thread.join(3)
        assert errors == ["rejected_before_application_input"]
    finally:
        listener.close()


def test_real_tls_device_session_and_stop_without_hardware(tmp_path):
    key = secrets.token_bytes(32)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1",0))
        port = probe.getsockname()[1]
    path = tmp_path/"pairing.json"
    info = {"device_id": "123456789abc", "identity": "aikvm-123456789abc", "controller_ip": "127.0.0.1", "port": port}
    save_pairing(path,info,key)
    received, errors = [], []
    def board_transport_fixture():
        deadline = time.monotonic()+5
        while True:
            try:
                raw = socket.create_connection(("127.0.0.1",port),timeout=1)
                break
            except ConnectionRefusedError:
                if time.monotonic()>deadline:
                    errors.append("listener_not_started")
                    return
                time.sleep(0.02)
        try:
            with client_context(info["identity"],key).wrap_socket(raw,server_hostname=None) as connection:
                stream = connection.makefile("rwb")
                while line := stream.readline():
                    request = json.loads(line)
                    received.append(request)
                    result = {"ok": True}
                    if request["op"] == "hello":
                        result.update(protocol=1, session="test-session", device_id=info["device_id"], transport="tls-psk", usb_profile="bios", hid_ready=True)
                    if request["op"] == "ping":
                        result["armed"] = True
                    if "seq" in request:
                        result["seq"] = request["seq"]
                    stream.write(json.dumps(result).encode()+b"\n")
                    stream.flush()
        except OSError:
            pass
    thread = threading.Thread(target=board_transport_fixture,daemon=True)
    thread.start()
    device = WirelessDevice(path,wait_seconds=5)
    try:
        device.arm()
        device.type_text("test")
        assert device.info["transport"] == "tls-psk"
        assert device.stop()["release_acknowledged"]
        assert [p["text"] for p in received if p["op"]=="type"] == list("test")
        assert not device.armed
    finally:
        device.close()
    thread.join(3)
    assert not errors


def test_provisioning_reuses_key_after_lost_ack(tmp_path):
    device, serial = make_device()
    original_read = serial.readline
    def read(limit):
        raw = original_read(limit)
        if not raw:
            return raw
        response = json.loads(raw)
        if serial.writes[-1]["op"]=="hello":
            response.update(device_id="123456789abc",transport="usb-cdc")
        if serial.writes[-1]["op"]=="provision":
            response["state"]="paired"
        return json.dumps(response).encode()+b"\n"
    serial.readline = read
    path = tmp_path/"pairing.json"
    try:
        from aikvm.device import Device, DeviceError
        serial.drop = "provision"
        with pytest.raises(DeviceError,match="Acknowledgment missing"):
            provision(device,path,"127.0.0.1",8787,"test-network","not-a-real-password")
        _, key = load_pairing(path)
        assert load_pairing(path)[0]["state"] == "provisioning_pending"
        serial.drop = None
        device = Device("fixture",serial_factory=lambda *a,**kw:serial)
        provision(device,path,"127.0.0.1",8787,"test-network","not-a-real-password")
        assert load_pairing(path)[1] == key
        sent = [p for p in serial.writes if p["op"]=="provision"]
        assert sent[0]["psk"] == sent[1]["psk"]
        assert "not-a-real-password" not in path.read_text()
        assert load_pairing(path)[0]["state"] == "provisioned"
    finally:
        device.close()
