# AI KVM

Ai anything in the world at this point using a cheap SOC ? This combo is two basic pieces. An ESP32s3 for the "hands" acting as a keyboard and mouse, and the "eyes" are a video capture card (hdmi-> USB in) or, surprisingly, a cheap-ish 1080P webcam pointed at the screen. Both paths are proven to work in my setup, YMMY. 
***See the diagram below*** 


A **Seeed Studio XIAO ESP32S3** sends USB keyboard and mouse reports. The published firmware build is version 0.2.1; installed devices may run an earlier version. An external capture device supplies images. You can operate the target through the local console or connect a vision-capable AI client through MCP. The bridge makes no model calls; the ESP32 handles input.

```text
Target video --> HDMI-to-USB capture --> Windows controller --> Console or MCP client
Target USB   <-- XIAO ESP32S3        <-- Paired Wi-Fi commands <-- Windows controller
```

The controller stays running while the target restarts. That makes preboot work possible, but each target still needs a usable video path and compatible USB HID behavior. Some laptops show BIOS only on their built-in display. An optical camera is a separate capture option and requires its own validation.

## Start here

For a separate target, you need the XIAO ESP32S3 with its antenna and a USB data cable, a Windows controller, a reachable 2.4GHz Wi-Fi network, and a capture device connected to the controller. The target must accept USB HID. Same-PC bench tests can use USB commands and desktop capture.

- **First setup:** follow [installation, flashing and pairing](docs/getting-started.md).
- **Already paired:** open the [console](#use-the-console).
- **AI control:** configure [local MCP](#local-mcp-control) and verify images and input in your chosen client.
- **BIOS acceptance:** record [navigation and reboot recovery](docs/getting-started.md#qualify-bios-and-reboot-recovery) for the actual target.

## What the evidence establishes

The implemented bench includes paired TLS Wi-Fi control, desktop and HID-only BIOS profiles, a manual console, four local MCP tools, and a qualification workflow. Hardware acceptance is specific to the tested setup.

The recorded MSI GL65 Leopard 10SFK test on **2026-10-27** captured a BIOS baseline and operator-confirmed DOWN navigation through an optical webcam. Direct HDMI BIOS capture was unavailable in that run. Reboot recovery was not verified, and the qualification receipt remains `complete: false`.

That record establishes a BIOS input path on one target. Full BIOS qualification still requires visible navigation and recovered input/video after reboot. The [documentation index](docs/README.md) separates operating instructions, design proposals and dated evidence.

On **2026-10-28**, the same target displayed its Windows desktop through a UGREEN 15389 HDMI capture device after OBS initialized the feed. With the board in `desktop` profile, an absolute pointer movement and both left and right clicks produced visible results. The board authenticated over Wi-Fi; 120 disarmed pings and three STOP requests were acknowledged across three sessions. These results do not establish BIOS video, reboot recovery, scroll or drag.

In a small live sample, 20 pointer submissions had a **19.6 ms median** acknowledgment round trip; 15 Shift presses had a **32.7 ms median**. Four recorded cursor moves showed the new position in frames received roughly 45–53 ms after acknowledgment. Host read times do not measure when the target rendered the change. A change-aware frame strategy and two-character typing chunks are under development; neither has been installed or qualified on the board. The model and full AI-client loop remain unmeasured.

## Use the console

For a controller that is already installed and paired, close other AI KVM or capture applications using the same board or camera, then run:

```powershell
.\.venv\Scripts\aikvm.exe console --pairing .local\pairing.json --camera 2 --target "MSI GL65 Leopard 10SFK"
```

Replace the example target name and camera index. Camera indexes can change when devices are connected; use `scripts/List-Devices.ps1` to check the available devices.

1. Verify that the preview shows the intended target.
2. Select **Connect input**, click the video and use the keyboard.
3. Select **Stop input** to release and disarm input.

The active USB profile appears beside the connection status. In `bios`, the console sends keyboard input only. In `desktop`, clicking the video also sends an absolute pointer click to the target. Keyboard translation assumes a US layout; the console sends key presses rather than sustained holds. Only one process can own the paired board.

To change profiles, close the console, run `aikvm profile --pairing .local\pairing.json desktop` or `bios`, then physically reconnect the board's target USB cable. Reflashing is unnecessary and would erase pairing.

The status line shows USB readiness, the last device response time and the last input acknowledgment. An acknowledgment confirms submission to USB; inspect the screen to learn what the target did. After an ambiguous acknowledgment, input stops and is never retried automatically. Inspect the target before reconnecting.

Video comes from the selected capture device. Recent frame receipts cannot distinguish a real target screen from a capture card's frozen or no-signal image. The firmware source includes Wi-Fi RSSI reporting; the recorded 0.2.0 installation lacks that field, so the console shows it as unavailable until compatible firmware is installed. A build alone does not establish installation or hardware validation.

Use the separate [`qualify` workflow](docs/getting-started.md#qualify-bios-and-reboot-recovery) to record BIOS navigation and reboot evidence.

## Local MCP control

The local bridge exposes four tools: `kvm_observe`, `kvm_act`, `kvm_status`, `kvm_stop`. It makes no model calls. The client must support MCP image results and a vision-capable model. Use USB/desktop capture for same-PC tests, or pairing/UVC for a separate target.

A local MCP client can use the definition in [mcp-config.example.json](mcp-config.example.json), after replacing the port. It starts **disarmed**. Add `--arm` to its `args` only when the operator authorizes physical input to this bench. Example foreground invocation:

```powershell
.\.venv\Scripts\aikvm.exe serve --port COM8 --target bench --capture desktop --arm
```

This is an MCP stdio process, so the client normally launches it. Stdout is reserved for MCP. `kvm_observe` returns a frame ID; `kvm_act` requires that frame and target ID. Frames expire for input after five seconds. Absolute coordinates use the returned image's pixels; crops map back to the full display. The bench rejects absolute desktop actions with multiple monitors. Relative movements are HID counts, not guaranteed pixels.

`kvm_stop` disarms. Restart the local process to rearm; the model has no arm tool. Explicit holds expire after approximately 1.5 seconds, even with a heartbeat. Loss of controller expires the device lease after approximately two seconds, plus bounded report processing. These are firmware timers, not hardware-measured latency guarantees. Missing acknowledgments close the connection and require inspection/restart; actions are never automatically resent.

The bridge cannot classify the consequences of every click. Arm it only for an operator-approved test. Unattended purchases, credential handling and external messages remain outside the qualified scope.

## Separate-target MCP and capture

The disarmed connection definition is in [mcp-config.wireless.example.json](mcp-config.wireless.example.json). After visually verifying the capture/input binding, a local MCP client can launch:

```powershell
.\.venv\Scripts\aikvm.exe serve --pairing .local\pairing.json --target target-pc --capture uvc --camera 0 --confirm-target-binding --arm
```

The bridge continuously reads frames, rejects stale host receipts and retries capture after disconnect. A dongle-generated black/no-signal/frozen image can be indistinguishable from genuine video. Signal validity remains unknown; host read timestamps do not prove sensor freshness. Omitting `--arm` leaves input disarmed. Armed UVC control requires the pairing transport and explicit binding confirmation. Close the qualification console before starting MCP; one process owns the paired link. In `bios`, use keyboard operations; return to `desktop` for absolute/relative pointer and full desktop input.

## Build, recover and inspect

The [setup guide](docs/getting-started.md#recovery-and-rebuild) contains rebuild checks, flash recovery and troubleshooting. The [bench contract](docs/bench-protocol.md) defines the wire protocol, action limits and remaining physical tests.

The [headless architecture](ai-kvm-headless-mcp-design.md) describes proposed extensions, including unattended workers and messaging adapters. Treat those as proposals until implemented and qualified.

## Primary references

- [Seeed XIAO ESP32S3 setup and download mode](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/)
- [Pinned Espressif board definitions](https://github.com/espressif/arduino-esp32/blob/3.3.2/boards.txt)
- [Pinned Espressif USB HID implementation](https://github.com/espressif/arduino-esp32/tree/3.3.2/libraries/USB)
- [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/)

The firmware is a new bench implementation using SDK libraries. No AirPlay/iPhone application sources were copied. Dependency notices remain in the installed toolchain; see [THIRD_PARTY.md](THIRD_PARTY.md).
