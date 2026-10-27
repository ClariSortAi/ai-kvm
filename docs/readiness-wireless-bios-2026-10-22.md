# Wireless and BIOS readiness — 2026-10-22

Today's scope is physical wireless input, real BIOS navigation and recovery after reboot on the selected target. Firmware 0.2.0 implements the transports/profiles and the controller includes executable qualification paths. Acceptance still requires the physical board, target and capture hardware; software checks are not a BIOS pass.

## Implemented

- One unpaired factory image for XIAO ESP32S3 8MB. Physical USB provisioning stores Wi-Fi/controller settings and a device-bound, random 256-bit PSK. The board initiates authenticated TLS 1.2 PSK to the controller; no unauthenticated board command listener exists.
- Controller pairing key protected with Windows current-user DPAPI. Wi-Fi password is prompted locally, transmitted over physical USB and not persisted in the controller pairing file. Board NVS is not flash-encrypted in this prototype.
- Shared command executor and active owner across USB/TLS. Bounded operations, duplicate-sequence cache, no automatic input retries, disconnect release, two-second lease and independent 1.5-second hold expiry remain implemented. STOP during connection cancels the pending arm.
- Persisted `desktop`, `bios` and `bios_mouse` profiles selected before USB initialization. `bios` is one HID-only boot keyboard with no report IDs and exactly eight-byte input reports. `bios_mouse` is an optional boot mouse diagnostic. No reflashing is required to change profiles.
- Wireless Windows host fixture, UVC/MCP control and a live BIOS qualification console. The console records baseline, before/after navigation, manual reboot, another visually confirmed navigation after reconnect, and recovered BIOS frames. A receipt completes only with explicit operator visual confirmation and the required evidence stages.
- A scoped firewall setup command, with read-only preview, resolves the real Python process image and limits the rule to the chosen local IP, adapter, current network profile, TCP port and local subnet. No firewall or network-trust change was made during preparation.

## Local verification

- Firmware compile and SHA256 image/source manifest: `artifacts/build.log`, `artifacts/firmware-manifest.json`.
- Linked ELF descriptor check (the ELF is a build output, not committed): `artifacts/usb-descriptor-check.json`; actual compiled BIOS keyboard map is 65 bytes, has no Report ID item and describes an eight-byte input packet. This proves the linked map, not target compatibility.
- 25 Python tests pass (report written locally by `pytest --junitxml=artifacts/tests.xml`; not committed). Tests include real loopback TLS sessions, rejection of unknown identity/wrong key, DPAPI round-trip, pairing-key preservation after a lost provisioning acknowledgment, input timeout without replay, partial typing, STOP during connection, typed operation bounds and observation mapping.
- Real stdio MCP transport/image smoke: `artifacts/mcp-smoke.json`. It retrieves/decodes a desktop crop without connecting or arming hardware.
- Python dependencies pass `pip check`; code compiles. GUI modules import with Tk 8.6. Live fixture/qualification GUI behavior requires hardware validation.

The TLS loopback fixture uses Python peers; it does not prove the ESP32 radio or ESP32/OpenSSL interoperability. Real board wireless host input is a required step today. Likewise, static descriptors and submitted HID reports cannot substitute for BIOS navigation evidence.

## Current physical boundary

Read-only inventory at preparation found no serial board or HDMI capture dongle; it showed only existing webcams/scanner. The target make/model and capture availability were requested. No device was flashed, no target reboot was initiated and no BIOS pass was recorded.

Use `README.md` for the concrete sequence: flash, USB host fixture, provision, scoped firewall setup if needed, wireless host fixture, select BIOS profile, move board to target USB, connect target HDMI capture, then run the qualification console. Keep per-device receipts under `artifacts` and do not mark qualification complete until those checks pass on the actual target.
