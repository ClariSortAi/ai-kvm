# Readiness receipt — 2026-10-22

Historical receipt for the initial USB-only milestone. Superseded the same day by `readiness-wireless-bios-2026-10-22.md` and firmware 0.2.0. The statements below describe that earlier build, not the current image.

Prepared on the Windows controller at `C:\Dev\AiKVM`. Target hardware is the plain Seeed XIAO ESP32S3 from the existing specification. No serial ports were enumerated at preparation time; no device was flashed and no physical input was emitted.

## Completed

- Workspace-local Arduino CLI 1.3.1, Espressif Arduino core 3.3.2 and ArduinoJson 7.4.2 installed.
- `firmware/aikvm/aikvm.ino` compiled successfully with `esp32:esp32:XIAO_ESP32S3:USBMode=default,CDCOnBoot=default`.
- Compiler storage/RAM figures are recorded in `artifacts/build.log`. The merged flash image is 8388608 bytes.
- esptool 5.1.0 identified the application as ESP32-S3, 8MB, with valid image checksum and validation hash.
- SHA256 hashes recorded in `artifacts/firmware-manifest.json`; all four binary hashes verified by both `aikvm doctor` and the flash script's `-CheckOnly` path.
- Python 3.14 environment installed; `pip check` passed. Installed dependencies are captured in `requirements.lock.txt`.
- 19 controller/MCP tests passed. They cover disarmed input, missing acknowledgments without replay/reconnect, partial typing, STOP, JSON newline framing, typed action limits, stale/wrong-target frames, display geometry/crop mapping, concurrent-action rejection and capture failure after input submission.
- A real stdio subprocess exposed the four MCP tools, returned a 64x64 desktop crop, and produced a PNG that the client decoded. No screenshot bytes were persisted in the receipt. No device was connected or armed.
- PowerShell scripts parsed successfully; the flasher's check-only path also passed under Windows PowerShell 5.1. The host GUI fixture imports under installed Tk 8.6; its live hardware flow is untested.

## Arrival path

Use `README.md`: verify board identity, enter BOOT/download mode, identify its COM port, run the backup-and-flash script, reconnect normally, identify the runtime COM port, run `info`, then run `bench` and click Start. The fixture creates a device-specific host-event receipt. Preserve that receipt alongside the flash log and manifest.

## Boundary

This is a prepared **same-PC USB bench** and local MCP bridge. It does not yet implement paired wireless transport, a qualified HID-only/BIOS profile, unattended task approvals, messaging or factory acceptance. UVC capture code is installed but no capture dongle or target video signal was qualified. No specific AI client's image delivery/input loop has been accepted. The earlier product design remains broader than this bench milestone.

Exact artifact hashes belong to the manifest; live hardware results belong to dated host fixture receipts. Neither compilation nor a tool acknowledgment establishes host input reception.
