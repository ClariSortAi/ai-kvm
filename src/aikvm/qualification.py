"""Live BIOS evidence collection. Operator judgments are explicit in receipts."""
from __future__ import annotations

import hashlib
import json
import queue
import threading
import time
from pathlib import Path

from .capture import Capture
from .core import Core, PressAction
from .wireless import WirelessDevice


NAVIGATION_KEYS = ("TAB", "LEFT", "RIGHT", "UP", "DOWN")


def diagnostic_key(device, key: str, watching_physical_bios: bool) -> dict:
    """One operator-observed key; never creates video qualification evidence."""
    if not watching_physical_bios:
        raise ValueError("Confirm you are watching the physical target's BIOS first")
    if key not in NAVIGATION_KEYS:
        raise ValueError("Diagnostic keys are limited to TAB and arrows")
    if device.info.get("usb_profile") != "bios" or not device.info.get("hid_ready"):
        raise ValueError("BIOS profile and enumerated target USB HID are required")
    result = device.send("press", keys=[key])
    return {"key": key, "input_result": result, "host_outcome_verified": False,
            "video_verified": False, "qualification_evidence": False,
            "observation_source": "operator_watching_physical_bios"}


def run(pairing: str, camera: int, target: str):
    import tkinter as tk
    from tkinter import messagebox
    from PIL import ImageTk

    root = tk.Tk()
    root.title(f"AI KVM — BIOS qualification — {target}")
    root.geometry("1080x860")
    capture = Capture("uvc", camera=camera, target=target)
    capture._start_uvc()
    device = WirelessDevice(pairing)
    core = Core(device, capture, target)
    directory = Path(__file__).resolve().parents[2]/"artifacts"/f"qualification-{time.strftime('%Y%m%d-%H%M%S')}"
    directory.mkdir(parents=True)
    events, pending = [], queue.Queue()
    busy = False
    last_navigation = None
    status = tk.StringVar(value="Check the preview against the physical target. No input is armed.")
    binding = tk.BooleanVar(value=False)
    physical_bios = tk.BooleanVar(value=False)
    connection_status = tk.StringVar(value="Input disarmed")
    image_label = tk.Label(root, bg="#16202b", fg="white", text="Waiting for capture; signal validity requires visual confirmation")
    image_label.pack(fill="both", expand=True, padx=12, pady=8)
    tk.Label(root, textvariable=status, wraplength=1030).pack(padx=12, pady=6)
    tk.Label(root, textvariable=connection_status).pack()
    tk.Checkbutton(root, text=f"I verified the paired USB board belongs to {target}; I will verify video before recording BIOS evidence", variable=binding).pack()
    controls = tk.Frame(root)
    controls.pack(pady=6)
    diagnostic_controls = tk.Frame(root)
    diagnostic_controls.pack(pady=4)
    log = tk.Text(root, height=8, font=("Consolas", 10))
    log.pack(fill="x", padx=12, pady=8)

    def persist():
        receipt = {"target": target, "device": device.info, "camera_index": camera, "events": events,
                   "judgment_source": "operator_visual_confirmation_with_saved_frames",
                   "qualification_scope": "this_target_firmware_usb_port_and_capture_path_only",
                   "complete": all(any(e.get("event")==name and e.get("passed") for e in events)
                                   for name in ("baseline_bios", "bios_navigation", "post_reboot_navigation", "reboot_recovered"))}
        (directory/"receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    def record(event, passed=None, **detail):
        entry = {"event": event, "timestamp_unix": time.time(), **detail}
        if passed is not None:
            entry["passed"] = passed
        events.append(entry)
        log.insert("end", f"{event}: {detail}\n")
        log.see("end")
        persist()

    def save_frame(observation, name):
        data = observation.png()
        filename = f"{len(events):03d}-{name}-{observation.id[:8]}.png"
        (directory/filename).write_bytes(data)
        return {"file": filename, "sha256": hashlib.sha256(data).hexdigest(), **observation.metadata()}

    def worker(operation, done):
        nonlocal busy
        if busy:
            status.set("An operation is already executing; no input queued.")
            return
        busy = True
        def execute():
            try:
                pending.put((done, operation(), None))
            except Exception as exc:
                pending.put((done, None, str(exc)))
        threading.Thread(target=execute, daemon=True).start()

    def connect():
        nonlocal device, core
        if not binding.get():
            status.set("Verify the physical capture/input binding first.")
            return
        if device.fault:
            device.close()
            device = WirelessDevice(pairing)
            core = Core(device, capture, target)
        def operation():
            info = device.connect()
            if info.get("usb_profile") != "bios":
                device.close()
                raise ValueError("Select profile bios, then reconnect target USB before BIOS keyboard qualification")
            if not info.get("hid_ready"):
                device.close()
                raise ValueError("Target USB HID has not enumerated. Wait for target power, then reconnect.")
            device.arm()
            return info
        def done(info):
            nonlocal last_navigation
            last_navigation = None
            record("wireless_connected", True, device_id=info["device_id"], transport=info["transport"],
                   usb_profile=info["usb_profile"], host_protocol=info["host_protocol"])
            status.set("Wireless input armed for this target. Record the visible BIOS baseline before navigation.")
        status.set("Waiting up to 30 seconds for the paired board…")
        worker(operation, done)

    def record_baseline():
        if not binding.get() or not device.armed:
            status.set("Verify binding and connect/arm the paired board first.")
            return
        if not messagebox.askyesno("Confirm BIOS", "Does the preview show the actual target's BIOS/UEFI screen?"):
            return
        worker(lambda: capture.grab(), lambda obs: record("baseline_bios", True, frame=save_frame(obs,"bios-baseline")))

    def navigate(key):
        nonlocal last_navigation
        if not binding.get() or not device.armed:
            status.set("No key sent: verify the target binding and Connect / arm first.")
            return
        if not any(e["event"]=="baseline_bios" for e in events):
            status.set("No key sent: record a visible BIOS baseline first, or use the physical-screen diagnostic below.")
            return
        def operation():
            before = capture.grab()
            result, after = core.act(target, before.id, PressAction(op="press", keys=[key]))
            return before, result, after
        def done(result):
            nonlocal last_navigation
            before, ack, after = result
            detail = {"key": key, "input_result": ack, "timestamp_unix": time.time(), "before": save_frame(before,"before-key")}
            if after:
                detail["after"] = save_frame(after,"after-key")
            record("navigation_attempt", **detail)
            last_navigation = detail if after else None
            status.set("Inspect the visible result. Confirm only if BIOS focus/selection moved as intended.")
        worker(operation, done)

    def diagnose(key):
        nonlocal last_navigation
        if busy:
            status.set("An operation is already executing; no input queued.")
            return
        if not binding.get() or not device.armed or not physical_bios.get():
            status.set("No key sent: verify target binding, Connect / arm, and confirm you are watching the physical BIOS.")
            return
        last_navigation = None
        watching = physical_bios.get()
        record("diagnostic_key_requested", key=key, qualification_evidence=False)
        def done(result):
            record("diagnostic_key_attempt", **result)
            status.set(f"{key} acknowledged by board. Check the target PC's physical screen; host outcome is unverified. This does not qualify BIOS video.")
        worker(lambda: diagnostic_key(device, key, watching), done)

    def entry_key():
        if not binding.get() or not device.armed:
            status.set("Verify binding and connect/arm before sending a firmware entry key.")
            return
        key = selected_entry.get()
        if not messagebox.askyesno("Firmware entry", f"Send {key} to this target during firmware startup?"):
            return
        worker(lambda: device.send("press", keys=[key]), lambda result: record("firmware_entry_key", key=key, input_result=result))

    def confirm_navigation():
        if not last_navigation:
            status.set("No completed navigation observation to verify.")
            return
        if messagebox.askyesno("Verify host outcome", "Did the intended BIOS focus/selection move after that key?"):
            record("bios_navigation", True, operator_confirmed=True, attempt=last_navigation)
            reboots = [e["timestamp_unix"] for e in events if e["event"]=="reboot_started"]
            if reboots and last_navigation["timestamp_unix"] > reboots[-1]:
                record("post_reboot_navigation", True, operator_confirmed=True, attempt=last_navigation)

    def reboot_start():
        if not any(e["event"]=="bios_navigation" and e.get("passed") for e in events):
            status.set("Verify BIOS navigation before the reboot recovery test.")
            return
        def operation():
            release = device.stop()
            device.close()
            return release
        def done(release):
            nonlocal last_navigation
            last_navigation = None
            record("reboot_started", release=release)
            status.set("Manually restart the target. Keep HDMI/USB connected. Then click Connect / arm again and record recovered BIOS.")
        worker(operation, done)

    def recovered():
        if not any(e["event"]=="reboot_started" for e in events) or not device.armed:
            status.set("Record reboot start, restart target, then reconnect and arm first.")
            return
        last_reboot = max(e["timestamp_unix"] for e in events if e["event"]=="reboot_started")
        if not any(e["event"]=="post_reboot_navigation" and e.get("passed") and e["timestamp_unix"] > last_reboot for e in events):
            status.set("After reconnecting, send a harmless key and confirm its visible result before recording recovery.")
            return
        if not messagebox.askyesno("Confirm recovery", "Has the target rebooted, and does the preview now show its live BIOS screen?"):
            return
        worker(lambda: capture.grab(), lambda obs: record("reboot_recovered", True, operator_confirmed=True,
                                                         frame=save_frame(obs,"recovered-bios")))

    def stop():
        device.cancel.set()
        device.cancel_wait()
        # STOP may interrupt a typing/key worker. It is never put behind its work queue.
        def run_stop():
            result = device.stop()
            pending.put((lambda value: record("stop", **value), result, None))
        threading.Thread(target=run_stop, daemon=True).start()
        status.set("STOP requested. Inputs disarmed; unplug is the physical fallback.")

    def tick():
        nonlocal busy
        connection_status.set(
            f"Input {'ARMED' if device.armed else 'DISARMED'} | USB HID ready: {device.info.get('hid_ready', 'unknown')} | "
            f"Protocol: {device.info.get('host_protocol', 'unknown')}" + (f" | {device.fault}" if device.fault else ""))
        while True:
            try:
                done, result, error = pending.get_nowait()
            except queue.Empty:
                break
            busy = False
            if error:
                record("operation_error", False, detail=error)
                status.set(error)
            else:
                done(result)
        with capture._lock:
            latest = capture._latest
        if latest and time.monotonic()-latest[2] < 0.75:
            preview = latest[0].copy()
            preview.thumbnail((1040, 540))
            photo = ImageTk.PhotoImage(preview)
            image_label.configure(image=photo, text="")
            image_label.image = photo
        elif not latest or time.monotonic()-latest[2] >= 0.75:
            image_label.configure(image="", text="No fresh host-received frame. Check capture connection and target output.")
        root.after(100, tick)

    tk.Button(controls,text="Connect / arm",command=connect).pack(side="left",padx=4)
    tk.Button(controls,text="Record BIOS baseline",command=record_baseline).pack(side="left",padx=4)
    for key in NAVIGATION_KEYS:
        tk.Button(controls,text=key,command=lambda value=key:navigate(value)).pack(side="left",padx=2)
    tk.Button(controls,text="Confirm navigation",command=confirm_navigation).pack(side="left",padx=4)
    tk.Checkbutton(diagnostic_controls, text="I am watching the physical BIOS (diagnostic only)", variable=physical_bios).pack(side="left")
    for key in NAVIGATION_KEYS:
        tk.Button(diagnostic_controls, text=f"Test {key}", command=lambda value=key:diagnose(value)).pack(side="left", padx=2)
    controls2 = tk.Frame(root)
    controls2.pack(pady=4)
    tk.Button(controls2,text="Record reboot start",command=reboot_start).pack(side="left",padx=5)
    tk.Button(controls2,text="Record recovered BIOS",command=recovered).pack(side="left",padx=5)
    tk.Button(controls2,text="STOP / release",command=stop,bg="#efb9b9").pack(side="left",padx=5)
    tk.Label(controls2,text=f"Evidence: {directory}").pack(side="left",padx=5)
    entry_controls = tk.Frame(root)
    entry_controls.pack(pady=4)
    selected_entry = tk.StringVar(value="F2")
    tk.OptionMenu(entry_controls,selected_entry,"F1","F2","F10","F12","ESC","DELETE").pack(side="left")
    tk.Button(entry_controls,text="Send firmware entry key",command=entry_key).pack(side="left",padx=5)

    def close():
        device.cancel.set()
        device.cancel_wait()
        core.close()
        persist()
        root.destroy()
    root.bind("<Escape>",lambda event:stop())
    root.protocol("WM_DELETE_WINDOW",close)
    tick()
    try:
        root.mainloop()
    finally:
        core.close()
        persist()
