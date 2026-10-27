"""Opt-in fixture: verifies host events, never claims BIOS/remote acceptance."""
from __future__ import annotations

import ctypes
import json
import time
from pathlib import Path

from .capture import Capture
from .device import Device


def run(port: str | None, input_device=None):
    import tkinter as tk
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    root.title("AI KVM — host acceptance bench")
    root.geometry("760x620+80+80")
    root.attributes("-topmost", True)
    device = input_device or Device(port)
    capture = Capture()
    results = []
    events = {"left": 0, "right": 0, "middle": 0, "wheel": 0, "shift_up": 0}
    started = False
    stopped = False
    label = tk.StringVar(value="Connect one XIAO. Close other controllers. Click Start to authorize this test.")
    tk.Label(root, textvariable=label, wraplength=720, font=("Segoe UI", 11)).pack(pady=12)
    text = tk.Text(root, height=4, font=("Consolas", 14))
    text.pack(fill="x", padx=20)
    canvas = tk.Canvas(root, width=680, height=210, bg="#e1ecf7")
    canvas.pack(padx=20, pady=10)
    canvas.create_text(340, 100, text="Mouse test surface — keep this window visible", font=("Segoe UI", 14))
    log = tk.Text(root, height=7, state="disabled", font=("Consolas", 10))
    log.pack(fill="x", padx=20)
    for number, name in ((1, "left"), (2, "middle"), (3, "right")):
        canvas.bind(f"<ButtonPress-{number}>", lambda event, key=name: events.__setitem__(key, events[key]+1))
    canvas.bind("<MouseWheel>", lambda event: events.__setitem__("wheel", events["wheel"]+event.delta))
    root.bind("<KeyRelease-Shift_L>", lambda event: events.__setitem__("shift_up", events["shift_up"]+1))

    def record(test, passed, detail=""):
        result = {"test": test, "passed": bool(passed), "detail": detail}
        results.append(result)
        log.configure(state="normal")
        log.insert("end", f"{'PASS' if passed else 'FAIL'}  {test}  {detail}\n")
        log.see("end")
        log.configure(state="disabled")
        return passed

    def save():
        directory = Path(__file__).resolve().parents[2]/"artifacts"
        directory.mkdir(exist_ok=True)
        path = directory/f"host-bench-{time.strftime('%Y%m%d-%H%M%S')}.json"
        path.write_text(json.dumps({"device": device.info, "timestamp_unix": time.time(), "results": results,
                                   "scope": "same_pc_windows_host_events", "bios_tested": False,
                                   "wireless_tested": device.info.get("transport")=="tls-psk"}, indent=2), encoding="utf-8")
        return path

    def halt():
        nonlocal stopped
        stopped = True
        status = device.stop()
        label.set(f"Stopped. Release acknowledgment: {status['release_acknowledged']}. Unplug for physical stop.")

    def focused():
        if root.focus_displayof() is None:
            raise RuntimeError("Bench lost focus; input stopped")

    def schedule(callback, delay=250):
        def guarded():
            if stopped:
                return
            try:
                focused()
                callback()
            except Exception as exc:
                record("bench_execution", False, str(exc))
                halt()
                path = save()
                label.set(f"Test stopped: {exc}. Results: {path}")
        root.after(delay, guarded)

    def start():
        nonlocal started
        if started:
            return
        started = True
        start_button.configure(state="disabled")
        try:
            info = device.connect()
            if not info["hid_ready"]:
                raise RuntimeError("HID not enumerated; reconnect and wait, then restart bench")
            device.arm()
            text.delete("1.0", "end")
            text.focus_set()
            label.set("Input authorized. Testing in three seconds. Keep this window focused; Escape stops.")
            schedule(type_phase, 3000)
        except Exception as exc:
            record("connect_and_arm", False, str(exc))
            halt()

    def type_phase():
        if root.focus_get() != text:
            raise RuntimeError("Test text field lost focus")
        device.type_text("AI KVM 123 !? abc XYZ")
        schedule(check_text)

    def check_text():
        if not record("host_text", text.get("1.0", "end-1c") == "AI KVM 123 !? abc XYZ", "Exact host text, US layout"):
            raise RuntimeError("Text mismatch; check keyboard layout/Caps Lock")
        device.send("press", keys=["CTRL", "a"])
        device.type_text("shortcut OK")
        schedule(check_shortcut)

    def check_shortcut():
        if not record("host_shortcut", text.get("1.0", "end-1c") == "shortcut OK", "Ctrl+A selected and replaced text"):
            raise RuntimeError("Shortcut did not reach host")
        obs = capture.grab()
        record("desktop_capture", obs.image.width > 0 and obs.image.height > 0, f"{obs.image.width}x{obs.image.height}")
        canvas.focus_set()
        x, y = canvas.winfo_rootx()+340, canvas.winfo_rooty()+100
        hx, hy = capture.resolve_point(obs.id, x-obs.geometry[0], y-obs.geometry[1])
        device.send("move_abs", x=hx, y=hy)
        schedule(lambda: check_absolute(x, y))

    def check_absolute(x, y):
        actual = root.winfo_pointerxy()
        if not record("host_absolute_pointer", abs(actual[0]-x) <= 8 and abs(actual[1]-y) <= 8, f"Expected {x},{y}; received {actual}"):
            raise RuntimeError("Absolute mapping failed; no click sent")
        before = actual
        device.send("move", dx=30, dy=0)
        schedule(lambda: check_relative(before))

    def check_relative(before):
        actual = root.winfo_pointerxy()
        if not record("host_relative_pointer", actual[0] > before[0], "Positive X movement observed; counts are not pixels"):
            raise RuntimeError("Relative pointer did not move")
        # Small motion remains inside the dedicated canvas on the single-monitor bench.
        if not (canvas.winfo_rootx() < actual[0] < canvas.winfo_rootx()+canvas.winfo_width()
                and canvas.winfo_rooty() < actual[1] < canvas.winfo_rooty()+canvas.winfo_height()):
            raise RuntimeError("Pointer outside test surface; no click sent")
        device.send("click", button="left")
        device.send("click", button="right")
        device.send("click", button="middle")
        device.send("scroll", ticks=1)
        schedule(check_mouse)

    def check_mouse():
        for name in ("left", "right", "middle", "wheel"):
            record(f"host_{name}", events[name] != 0, "Host event received")
        label.set("Testing held Shift release by STOP, then a silent controller lease expiry.")
        device.send("key_down", key="SHIFT")
        schedule(stop_hold, 200)

    def stop_hold():
        before = events["shift_up"]
        status = device.stop()
        record("stop_ack", status["release_acknowledged"])
        schedule(lambda: check_stop(before))

    def check_stop(before):
        record("host_stop_release", events["shift_up"] > before, "Host Shift release after STOP")
        device.arm()
        device.send("key_down", key="SHIFT")
        # Silence the heartbeat without closing CDC: firmware must release on its own.
        device._quit.set()
        before = events["shift_up"]
        schedule(lambda: check_lease(before), 2800)

    def check_lease(before):
        from .device import DeviceError
        record("host_hold_expiry", events["shift_up"] > before, "Host release within 2.8s; precise latency not measured")
        try:
            with device.lock:
                reply = device._exchange({"v": 1, "session": device.info["session"], "op": "ping"})
            record("expired_session_rejected", False, f"Unexpected reply {reply}")
        except DeviceError as exc:
            record("expired_session_rejected", "invalid_session" in str(exc), str(exc))
        finish()

    def finish():
        device.close()
        path = save()
        passed = all(result["passed"] for result in results)
        label.set(f"{'PASS' if passed else 'FAIL'} — Windows bench completed. Results: {path}")

    def close():
        halt()
        device.close()
        capture.close()
        root.destroy()

    controls = tk.Frame(root)
    controls.pack(pady=12)
    start_button = tk.Button(controls, text="Start input tests", command=start, width=22)
    start_button.pack(side="left", padx=10)
    tk.Button(controls, text="STOP / release-all", command=halt, width=22, bg="#f6caca").pack(side="left", padx=10)
    root.bind("<Escape>", lambda event: halt())
    root.protocol("WM_DELETE_WINDOW", close)
    try:
        root.mainloop()
    finally:
        device.close()
        capture.close()
