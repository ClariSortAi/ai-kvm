from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import getpass
from pathlib import Path

from serial.tools import list_ports

from .capture import Capture
from .core import Core
from .device import Device


def doctor():
    root = Path(__file__).resolve().parents[2]
    manifest_path = root / "artifacts/firmware-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig")) if manifest_path.exists() else None
    hashes = {}
    sources = {}
    if manifest:
        for name, expected in manifest["images"].items():
            path = root / "artifacts/firmware" / name
            hashes[name] = path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected
        for name, expected in manifest["sources"].items():
            path = root / "firmware/aikvm" / name
            sources[name] = path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected
    import ssl
    return {"ports": [{"port": p.device, "description": p.description, "vid": p.vid, "pid": p.pid,
                       "serial_number": p.serial_number} for p in list_ports.comports()],
            "firmware_manifest": str(manifest_path), "firmware_version": manifest.get("firmware_version") if manifest else None,
            "image_hashes_valid": hashes, "source_hashes_match_image_manifest": sources,
            "tls_psk_available": bool(getattr(ssl,"HAS_PSK",False)),
            "packages": {name: importlib.metadata.version(name) for name in ("mcp", "pyserial", "mss", "Pillow", "opencv-python")},
            "hardware_tested": False}


def main():
    parser = argparse.ArgumentParser(prog="aikvm")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Read-only toolchain/artifact/serial inventory")
    info = commands.add_parser("info", help="Connect and inspect firmware; never arms")
    def transport(command):
        group = command.add_mutually_exclusive_group(required=True)
        group.add_argument("--port", help="Physical USB CDC COM port")
        group.add_argument("--pairing", help="DPAPI-protected pairing file; listen for the board over TLS")
    transport(info)
    bench = commands.add_parser("bench", help="Open the opt-in host input acceptance fixture")
    transport(bench)
    setup = commands.add_parser("provision", help="Pair Wi-Fi over physical USB; passwords are prompted locally")
    setup.add_argument("--port", required=True)
    setup.add_argument("--controller-ip", required=True)
    setup.add_argument("--listen-port", type=int, default=8787)
    setup.add_argument("--pairing", default=".local/pairing.json")
    profile = commands.add_parser("profile", help="Select the USB profile for the next physical USB reconnection")
    transport(profile)
    profile.add_argument("profile", choices=("desktop", "bios", "bios_mouse"))
    qualify = commands.add_parser("qualify", help="Live target-video and BIOS qualification console")
    qualify.add_argument("--pairing", required=True)
    qualify.add_argument("--camera", type=int, default=0)
    qualify.add_argument("--target", required=True, help="Actual target make/model or inventory name")
    serve = commands.add_parser("serve", help="Local stdio MCP bridge")
    transport(serve)
    serve.add_argument("--target", default="bench")
    serve.add_argument("--capture", choices=("desktop", "uvc"), default="desktop")
    serve.add_argument("--monitor", type=int, default=1)
    serve.add_argument("--camera", type=int, default=0)
    serve.add_argument("--arm", action="store_true", help="Operator explicitly authorizes input to the bench target")
    serve.add_argument("--confirm-target-binding", action="store_true", help="Operator verified this UVC feed belongs to the paired HID target")
    args = parser.parse_args()
    def selected_device():
        if getattr(args, "pairing", None):
            from .wireless import WirelessDevice
            return WirelessDevice(args.pairing)
        return Device(args.port)
    if args.command == "doctor":
        print(json.dumps(doctor(), indent=2))
    elif args.command == "info":
        device = selected_device()
        try:
            print(json.dumps(device.connect(), indent=2))
        finally:
            device.close()
    elif args.command == "bench":
        from .bench import run
        run(args.port, selected_device())
    elif args.command == "provision":
        from .wireless import provision
        device = Device(args.port)
        try:
            ssid = input("2.4GHz Wi-Fi SSID: ")
            password = getpass.getpass("Wi-Fi password (not echoed): ")
            print(json.dumps(provision(device, Path(args.pairing), args.controller_ip, args.listen_port, ssid, password), indent=2))
        finally:
            device.close()
    elif args.command == "profile":
        device = selected_device()
        try:
            info = device.connect()
            with device.lock:
                print(json.dumps(device._exchange({"v": 1, "op": "profile", "session": info["session"], "profile": args.profile}), indent=2))
        finally:
            device.close()
    elif args.command == "qualify":
        from .qualification import run
        run(args.pairing, args.camera, args.target)
    elif args.command == "serve":
        from .server import make_server
        if args.capture == "uvc" and args.arm and (not args.pairing or not args.confirm_target_binding):
            parser.error("UVC input requires --pairing and --confirm-target-binding after checking the actual target preview")
        core = Core(selected_device(), Capture(args.capture, args.monitor, args.camera, args.target), args.target)
        core.mode = "wireless_target" if args.pairing else "usb_same_pc"
        try:
            if args.arm:
                core.device.arm()
            make_server(core).run()
        finally:
            core.close()


if __name__ == "__main__":
    main()
