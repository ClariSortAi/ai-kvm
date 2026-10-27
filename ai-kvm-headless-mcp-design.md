# Headless AI KVM: input and vision through MCP

Proposed architecture, 2026-10-20. This records the clarified product direction.
Firmware 0.2.0 was built on 2026-10-22 with paired TLS Wi-Fi control and HID-only
BIOS profiles; see `README.md` and `docs/readiness-wireless-bios-2026-10-22.md`.
Today's hardware qualification requires the board, actual target and video capture.

## Product boundary

The user supplies an existing vision-capable AI agent. Our product supplies
physical keyboard/mouse control and observations of the target screen through
MCP. No model runs on the ESP32. No proprietary agent loop or model subscription
is required.

For this MVP, a working computer runs a small headless MCP bridge. The target
computer needs no installed agent and no network connection.

## Physical connections

```text
Target HDMI output --> HDMI-to-USB UVC capture --> Working computer
Target USB port    <-- ESP32 USB HID            <-- authenticated Wi-Fi commands
                                                       from working computer

User's AI agent <--> MCP bridge on working computer
                    |-- capture driver --> target screen images
                    `-- device driver  --> ESP32 keyboard/mouse actions
```

The capture device plugs into the working computer, not the ESP32. Capture
hardware receives HDMI; the working computer reads frames and returns images
through MCP. The ESP32 remains an input peripheral.

Use existing capture hardware for the prototype. A later enclosure can contain
both capture electronics and the ESP32, but packaging does not remove the
working computer or its capture USB connection.

Provision the ESP32's network and pairing credential once over physical USB
from the working computer before attaching it to the target.

## Minimal MCP contract

| Tool | Contract |
|---|---|
| `observe` | Return the latest available target frame as MCP image content, plus target ID, frame ID, capture timestamp, dimensions and signal/freshness status. Support a crop for small text. |
| `act` | Execute a bounded, typed keyboard/mouse operation against an explicit target and observation reference; then return execution status and a fresh observation, or an explicit observation timeout. |
| `status` | Report target binding, input connectivity, video signal and current control owner. |
| `stop` | Cancel queued input and release held keys/buttons; report whether release was acknowledged. |

`act` supports typing, key chords, pointer movement, clicks, scrolling and
bounded drag sequences. It is not an arbitrary shell command.

The user's agent supplies the loop: observe, reason, act, inspect the result.
The bridge executes tools and checks their constraints; it makes no model calls.

## What makes vision reliable

- Bind each capture source and ESP32 identity to the same configured target.
  Show a setup preview to verify that binding.
- Drain capture buffers continuously. Return recent observations with measured
  timestamps; never silently substitute an old frame during signal loss.
- Preserve screenshot-to-target coordinate mapping through resizing and crops.
  Prefer absolute pointer input where supported; retain keyboard and relative
  pointer fallback for firmware interfaces.
- Use frame references and age limits to reject obsolete coordinate actions.
  A frame reference cannot prove the target has not changed since capture.
- After input, obtain a new capture with a bounded settling period. Report
  input acknowledgment separately from visual evidence of success.
- Handle video-mode changes and capture reconnects across reboot. Treat no
  signal, timeout and a valid black image as distinct observations where the
  hardware exposes enough information.
- Allow one active controller; expire input control on disconnect. Device-side
  timeout releases held inputs even if the bridge disappears.

## Client and network boundary

MCP supports image tool results. The selected client must actually deliver those
images to a vision-capable model and support calling the input tools. Verify this
per client; text-only MCP support is insufficient.

Start with a local MCP client and a local bridge. Cloud-hosted clients require a
supported authenticated connection to that bridge. This is a transport adapter,
not a reason to add an inference service.

Headless means the bridge needs no persistent GUI. It still needs a running
working computer. Removing that computer requires a separate always-on capture
and network host; the ESP32 alone does not provide that function.

## Acceptance before claiming the loop works

1. In the selected AI client, retrieve and read the target's actual BIOS screen.
2. Navigate using a harmless key and verify the resulting screen through MCP.
3. Exercise pointer mapping, cropped text and a video resolution change.
4. Reboot the target; recover capture and input without target-side software.
5. Disconnect capture and command transport; report loss and release held input.

The target must expose a usable external video signal and accept USB HID.
An internal laptop display is not guaranteed to be mirrored externally during
firmware startup. Where external video is unavailable, a camera aimed at the
display is a separate, lower-fidelity capture option that requires calibration.

## References

- [MCP Python SDK: image tool results](https://py.sdk.modelcontextprotocol.io/servers/media/)
- [Openterface: capture and input connection example](https://docs.openterface.com/tutorial/kvm/01-getting-started/)
- Openterface and similar projects as prior art for capture/input architecture.
