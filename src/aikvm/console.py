"""Interactive controller for a paired target; qualification remains a separate tool."""
from __future__ import annotations

import queue
import threading
import time

from .capture import Capture
from .wireless import WirelessDevice


KEY_NAMES = {
    'Return': 'ENTER', 'Escape': 'ESC', 'Tab': 'TAB', 'BackSpace': 'BACKSPACE',
    'Delete': 'DELETE', 'Insert': 'INSERT', 'Home': 'HOME', 'End': 'END',
    'Prior': 'PAGEUP', 'Next': 'PAGEDOWN', 'Left': 'LEFT', 'Right': 'RIGHT',
    'Up': 'UP', 'Down': 'DOWN', 'space': 'SPACE',
    **{f'F{i}': f'F{i}' for i in range(1, 13)},
}


def keys_for_event(keysym: str, char: str, state: int) -> list[str] | None:
    """Translate a Tk keypress to the firmware's US keyboard vocabulary."""
    key = KEY_NAMES.get(keysym)
    if key is None and len(keysym) == 1 and keysym.isascii() and keysym.isalnum():
        key = keysym.lower()
    if key is None and len(char) == 1 and 32 <= ord(char) <= 126:
        key = char
    if key is None:
        return None
    modifiers = []
    if state & 0x4:
        modifiers.append('CTRL')
    if state & 0x8 or state & 0x20000:
        modifiers.append('ALT')
    if state & 0x1:
        modifiers.append('SHIFT')
    return [*modifiers, key]


def point_on_frame(x, y, view_width, view_height, frame_width, frame_height):
    """Map only points inside the displayed image to native frame pixels."""
    if min(view_width, view_height, frame_width, frame_height) <= 0:
        return None
    if not (0 <= x < view_width and 0 <= y < view_height):
        return None
    return (min(frame_width - 1, x * frame_width // view_width),
            min(frame_height - 1, y * frame_height // view_height))


def run(pairing: str, camera: int, target: str):
    import tkinter as tk
    from PIL import ImageTk

    root = tk.Tk()
    root.title(f'AI KVM — {target}')
    root.geometry('1080x760')
    root.minsize(600, 420)
    device = WirelessDevice(pairing)
    capture = Capture('uvc', camera=camera, target=target)
    capture._start_uvc()
    pending = queue.Queue()
    outstanding = 0
    closing = False
    stopping = False
    generation = 0
    actions = queue.Queue(maxsize=32)
    displayed = None
    last_frame = None
    last_size = None
    status = tk.StringVar(value='Video starting. Connect input when the preview shows your target.')
    connection = tk.StringVar(value='Input disconnected')
    telemetry = tk.StringVar(value='Board offline · Wi-Fi strength unavailable')

    bar = tk.Frame(root)
    bar.pack(fill='x', padx=12, pady=(10, 4))
    tk.Label(bar, text=target, font=('Segoe UI', 12, 'bold')).pack(side='left')
    tk.Label(bar, textvariable=connection).pack(side='left', padx=16)
    connect_button = tk.Button(bar, text='Connect input')
    connect_button.pack(side='right')
    tk.Button(bar, text='Stop input', command=lambda: stop()).pack(side='right', padx=8)
    screen = tk.Label(root, bg='#17212b', fg='white', text='Waiting for video…', takefocus=True)
    tk.Label(root, textvariable=telemetry, anchor='w').pack(fill='x', padx=12)
    screen.pack(fill='both', expand=True, padx=12, pady=6)
    tk.Label(root, textvariable=status, anchor='w', wraplength=1000).pack(fill='x', padx=12, pady=(0, 10))

    def action_loop():
        while True:
            item_generation, operation, done = actions.get()
            if item_generation != generation or closing:
                pending.put((item_generation, done, None, None))
                continue
            try:
                result = operation()
                pending.put((item_generation, done, result, None))
            except Exception as exc:
                pending.put((item_generation, done, None, str(exc)))

    threading.Thread(target=action_loop, daemon=True).start()

    def worker(operation, done=lambda result: None, allow_queue=False):
        nonlocal outstanding
        if closing or (outstanding and not allow_queue):
            status.set('Input is busy; action not sent.')
            return False
        try:
            actions.put_nowait((generation, operation, done))
        except queue.Full:
            status.set('Input queue is full; action not sent.')
            return False
        outstanding += 1
        return True

    def connect():
        nonlocal device
        if outstanding or stopping:
            return
        if device.armed:
            status.set('Input is already connected.')
            return
        if device.fault:
            device.close()
            device = WirelessDevice(pairing)
        connect_generation = generation
        def operation():
            info = device.connect()
            if not info.get('hid_ready'):
                raise RuntimeError('Target USB input is not ready. Check the board and target connection.')
            if connect_generation != generation:
                raise RuntimeError('Connection cancelled.')
            device.arm()
            if connect_generation != generation:
                device.stop()
                raise RuntimeError('Connection cancelled.')
            return info
        def done(info):
            status.set('Input connected. Click the video to focus, then use your keyboard. Verify actions on screen.')
        status.set('Waiting for the paired board…')
        worker(operation, done)

    connect_button.configure(command=connect)

    def stop():
        nonlocal generation, stopping
        if stopping:
            return
        stopping = True
        generation += 1
        device.cancel.set()
        device.cancel_wait()
        status.set('Stopping input…')
        def stopped(value):
            nonlocal stopping
            stopping = False
            status.set('Input stopped.' if value.get('release_acknowledged') else
                       'Input disconnected; release was not acknowledged. Check the target.')
        def perform():
            result = device.stop()
            pending.put((None, stopped, result, None))
        threading.Thread(target=perform, daemon=True).start()

    def send_key(event):
        keys = keys_for_event(event.keysym, event.char, event.state)
        if not keys:
            return 'break'
        if not device.armed:
            status.set('Connect input first.')
        elif displayed is None or time.monotonic() - displayed[2] >= 0.75:
            status.set('No fresh video. Input was not sent.')
        else:
            worker(lambda: device.send('press', keys=keys),
                   lambda result: status.set('Input sent. Check the target screen.'), allow_queue=True)
        return 'break'

    def click(event):
        screen.focus_set()
        if not device.armed:
            status.set('Connect input first.')
            return
        profile = device.info.get('usb_profile')
        if profile != 'desktop' or device.info.get('host_protocol') == 'boot':
            status.set(f'This {profile or "unknown"} profile does not support absolute pointer input. Keyboard is available.')
            return
        if displayed is None or time.monotonic() - displayed[2] >= 0.75:
            status.set('No fresh video. Input was not sent.')
            return
        image, _, _, generation, width, height = displayed
        x = event.x - (screen.winfo_width() - width) // 2
        y = event.y - (screen.winfo_height() - height) // 2
        point = point_on_frame(x, y, width, height, image.width, image.height)
        if point is None:
            return
        def operation():
            obs = capture.grab()
            if obs.geometry[4] != generation or (obs.image.width, obs.image.height) != image.size:
                raise RuntimeError('Video source changed. Inspect the preview and try again.')
            px, py = capture.resolve_point(obs.id, *point)
            device.send('move_abs', x=px, y=py)
            return device.send('click', button='left')
        worker(operation, lambda result: status.set('Click sent. Check the target screen.'))

    screen.bind('<KeyPress>', send_key)
    screen.bind('<Button-1>', click)

    def tick():
        nonlocal outstanding, displayed, last_frame, last_size
        if closing:
            return
        while True:
            try:
                item_generation, done, result, error = pending.get_nowait()
            except queue.Empty:
                break
            if item_generation is not None:
                outstanding -= 1
                if item_generation != generation:
                    continue
            if error:
                status.set(error)
            else:
                done(result)
        profile = device.info.get('usb_profile')
        connection.set(('Input connected' if device.armed else 'Input disconnected') +
                       (f' · {profile}' if profile else '') +
                       (' · USB not ready' if device.info.get('hid_ready') is False else ''))
        live = device.status()
        if device.armed and live['connected']:
            rssi = device.info.get('wifi_rssi_dbm')
            rtt = live.get('last_round_trip_ms')
            activity = live.get('last_input_ack_age_seconds')
            telemetry.set('ESP32 · USB ' + ('ready' if device.info.get('hid_ready') else 'not ready') +
                          f' · Wi-Fi {str(rssi) + " dBm" if rssi is not None else "strength unavailable"}' +
                          (f' · response {rtt:.0f} ms' if rtt is not None else '') +
                          (f' · input acknowledged {activity:.1f}s ago' if activity is not None else ''))
        else:
            telemetry.set('Board offline or input stopped · Wi-Fi strength unavailable')
        with capture._lock:
            latest = capture._latest
        if latest and time.monotonic() - latest[2] < 0.75:
            size = (max(1, screen.winfo_width()), max(1, screen.winfo_height()))
            if latest[2] != last_frame or size != last_size:
                preview = latest[0].copy()
                preview.thumbnail(size)
                photo = ImageTk.PhotoImage(preview)
                screen.configure(image=photo, text='')
                screen.image = photo
                displayed = (*latest, preview.width, preview.height)
                last_frame, last_size = latest[2], size
        else:
            displayed = None
            last_frame = None
            screen.configure(image='', text='No recent video. Check the capture connection and target output.')
            screen.image = None
        root.after(50, tick)

    def close():
        nonlocal closing, generation
        closing = True
        generation += 1
        device.cancel.set()
        device.cancel_wait()
        capture.close()
        # Release and close in a worker so a slow connection cannot freeze the window.
        threading.Thread(target=device.close).start()
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', close)
    tick()
    root.mainloop()
