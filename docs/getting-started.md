# Set up AI KVM and qualify a target

Start with the board on the controller. Prove USB input, pair Wi-Fi, then move the board to the target and test the screen you intend to control. Each step produces evidence for the next.

The examples assume a Windows checkout at `C:\Dev\AiKVM` and a plain **Seeed Studio XIAO ESP32S3 with 8MB flash**. Replace example COM ports, IP addresses, camera indexes and target names with your own. Keep pairing files, flash backups and captures local.

## Prepare the controller

Install Python 3.14 before running these commands. Wireless control requires Python 3.13 or newer with TLS-PSK support; `doctor` reports whether that support is available. Run from the repository root:

```powershell
Set-Location C:\Dev\AiKVM
py -3.14 -m venv .venv
.\scripts\Install-Python.ps1
.\scripts\Install-Toolchain.ps1
.\scripts\Build-Firmware.ps1
.\scripts\Flash-Device.ps1 -Port COM999 -CheckOnly
.\.venv\Scripts\aikvm.exe doctor
```

Create the virtual environment only for a fresh checkout. Preserve an existing environment or resolve its Python version before continuing. The installers download dependencies; build tools and Python packages stay in this workspace. Do not copy a virtual environment from another computer.

`-CheckOnly` checks the local image without opening a board. Review `doctor` for image hashes, source-to-manifest matches and TLS-PSK support. A successful build does not install firmware or prove hardware behavior.

`artifacts/firmware/aikvm.ino.merged.bin` is the complete 8MB image at flash offset `0x0`. The application-only `.bin` is not a complete first-flash image. Do not substitute it into the merged-image command.

## Flash and test USB input

1. Verify the board is **XIAO ESP32S3**, not ESP32C3/C6. Use a USB **data** cable. Connect only the board being tested to this Windows PC.
2. Enter download mode: disconnect USB, hold **BOOT**, connect USB, release BOOT. If necessary, hold BOOT, tap RESET, then release BOOT. Identify the new COM port:

   ```powershell
   Set-Location C:\Dev\AiKVM
   .\.venv\Scripts\aikvm.exe doctor
   ```

3. Replace `COM7` with that port. Flash the image you built and checked:

   ```powershell
   .\scripts\Flash-Device.ps1 -Port COM7
   ```

   The script verifies image hashes, checks for ESP32-S3, backs up the existing 8MB flash, then writes the full merged image. It leaves a flash log and backup in `artifacts`. The full image replaces previous flash contents. `-SkipBackup` is available for an explicitly disposable board; backup is the default. `-CheckOnly` validates local hashes without opening a device.

4. Disconnect/reconnect USB normally, without holding BOOT. The runtime COM port may differ. Run `doctor` again, then inspect firmware and launch the fixture using the runtime port:

   ```powershell
   .\.venv\Scripts\aikvm.exe info --port COM8
   .\.venv\Scripts\aikvm.exe bench --port COM8
   ```

5. Use one monitor for this first absolute-pointer test. Close other serial/MCP controllers. In the fixture, click **Start input tests** and keep its window focused. Escape or **STOP / release-all** disarms input. Unplugging the board is the physical stop.

The fixture checks exact typed text, Ctrl+A replacement, a desktop frame, absolute/relative movement, three mouse buttons, wheel events, held-key release after STOP, and held-input expiry with no heartbeat. It records host events and the firmware device ID in `artifacts/host-bench-*.json`. A protocol acknowledgment alone is not a pass. Non-US keyboard layouts and Caps Lock can make the text test fail; that is a compatibility result to investigate.

## Pair and test Wi-Fi

Attach the board's Wi-Fi antenna. Keep the board connected to the controller over USB in the default `desktop` profile for setup. The ESP32S3 joins a **2.4GHz** WPA network; the controller must be reachable on that network. Use a stable controller IPv4 address. `scripts/List-Devices.ps1` lists current network addresses, COM ports and camera names.

Provision over physical USB. Enter the network name/password at the local terminal prompts; do not paste them into chat:

```powershell
.\.venv\Scripts\aikvm.exe provision --port COM8 --controller-ip 192.168.1.50 --pairing .local\pairing.json
```

Replace the example IP and COM port. A random 256-bit pairing key is generated and protected on this Windows account with DPAPI. The Wi-Fi password is sent directly to the board and is not saved in the controller's pairing file. The board stores its Wi-Fi settings and pairing key in NVS; this prototype does not enable flash encryption. Pairing retries reuse the saved key, including after an ambiguous provisioning acknowledgment.

The board initiates an outbound **TLS 1.2 PSK** connection to the controller on TCP 8787. Both peers prove possession of the pairing key; unknown identities and incorrect keys fail before commands. There is no unauthenticated board TCP listener, certificate clock dependency, model call or cloud service. Python 3.13+ with PSK support is required for wireless; the recorded setup uses 3.14.

If Windows blocks inbound connections, run the following once in **Administrator PowerShell** from this folder:

```powershell
.\scripts\Enable-Wireless.ps1 -ControllerIP 192.168.1.50
```

Use the same controller IP as provisioning. The rule scopes TCP 8787 to that local IP, its adapter, the actual Python process executable, the local subnet and the adapter's current network profile. It does not change the network's trust category. `-CheckOnly` previews the exact rule without administrator access or mutation. Run one controller command at a time. With the board still attached to this PC, verify wireless input using the same host fixture:

```powershell
.\.venv\Scripts\aikvm.exe bench --pairing .local\pairing.json
```

Click Start. This checks host-received input over the actual board's Wi-Fi link. Close the fixture before continuing. A successful Python loopback TLS test does not substitute for this hardware receipt.

## Qualify BIOS and reboot recovery

Select the HID-only keyboard profile while USB setup is still available:

```powershell
.\.venv\Scripts\aikvm.exe profile --port COM8 bios
```

Disconnect the board from the controller. Connect it to the **target's USB port**. Connect target HDMI to the capture dongle and the dongle USB to the **controller**. No software is installed on the target. The selected profile takes effect at the next board restart/reconnection; Wi-Fi pairing is retained. A full-image reflash would erase those settings, so do not reflash merely to change profiles.

The `bios` profile exposes one boot keyboard interface, no CDC, no mouse collection and no report IDs. Its keyboard reports are exactly eight bytes in report and boot protocol. It handles SET_PROTOCOL, GET_REPORT, output LEDs and SET_IDLE. This keeps the desktop composite report layout out of the BIOS keyboard path. An optional `bios_mouse` profile provides a separate boot mouse diagnostic: five-byte report mode and three-byte boot mode. Keyboard navigation is the primary BIOS qualification path.

Open the qualification console, choosing the actual capture dongle's camera index and target name:

```powershell
.\.venv\Scripts\aikvm.exe qualify --pairing .local\pairing.json --camera 0 --target "Actual target make/model"
```

1. Check the preview against the physical target and tick the binding confirmation. Click **Connect / arm**.
2. Enter the target's BIOS/UEFI using its documented key. The console can send a chosen firmware entry key when the board is connected; a local keyboard can establish the initial BIOS screen if startup timing requires it.
3. Click **Record BIOS baseline** only when the preview shows the actual BIOS screen.
4. Send TAB or an arrow. Inspect the resulting screen, then click **Confirm navigation** only when the expected selection/focus moved.
5. Click **Record reboot start**, manually reboot the target, then click **Connect / arm** after it returns. Capture continues reading/reconnecting across the reboot.
6. Send another harmless key and confirm its visible result, then click **Record recovered BIOS**. The receipt cannot complete without confirmed input after reboot.
7. Use **STOP / release** when finished. Keep the board and capture connected until evidence is saved.

Evidence goes to `artifacts/qualification-<timestamp>/`: before/after PNGs, SHA256 references, device/profile identity, actions and a JSON receipt. Judgments are explicitly marked as operator-confirmed. A command acknowledgment or a changed image alone cannot mark BIOS qualification complete. A pass applies only to the tested target, firmware, USB port and capture path.

If HDMI shows **No Signal**, the normal TAB/arrow buttons send nothing until a visible BIOS baseline has been recorded. To isolate keyboard input, verify the paired board's target, connect/arm, and select **I am watching the physical BIOS (diagnostic only)** while an operator watches the laptop itself. **Test TAB/LEFT/RIGHT/UP/DOWN** sends one bounded key without requiring capture. The receipt distinguishes a requested key from a board-acknowledged attempt; neither proves visible navigation or counts toward qualification. No baseline should be recorded from a no-signal image. The live status line reports input arming, USB HID readiness, protocol and connection faults.

For profile recovery while wireless remains reachable:

```powershell
.\.venv\Scripts\aikvm.exe profile --pairing .local\pairing.json desktop
```

Reconnect the board to the controller to restore USB setup. If pairing/network access is unavailable, BOOT/download-mode reflashing remains the physical recovery path; full-image reflashing clears pairing.

## Recovery and rebuild

- Paired controller address unavailable: the board connects to the IP saved during provisioning. Reserve that address for the intended controller in DHCP, or reprovision through USB with the correct address. Editing `pairing.json` alone cannot change the board's destination. The `bios` profile has no USB serial interface; restore connectivity before selecting `desktop` for USB setup. A full-image reflash is a recovery operation that clears pairing.
- Capture returns frames but no target picture: identify the camera index again after reconnecting devices. A black frame or UGREEN logo proves only that the dongle returned an image. Check the target's HDMI output and its own screen before arming input; some targets do not output BIOS video over HDMI.
- No COM port: try another known data cable and direct USB port; repeat BOOT/RESET. Check Windows Device Manager before installing any driver. This board uses the ESP32-S3 native USB path; do not assume a CH340 driver is required.
- Flash connection failure: close the fixture/MCP/serial monitor, re-enter ROM download mode and recheck its COM port. The flasher deliberately uses `--before no-reset`; enter download mode physically first.
- No runtime HID/COM after flash: unplug/replug normally, then tap RESET. Re-enter ROM download mode if recovery is needed. ROM recovery does not require the bench firmware to run.
- To restore an original backup, enter ROM mode and run the installed esptool with `--chip esp32s3 --port COM7 --before no-reset write-flash 0` followed by the **exact** backup path. Verify the backup's SHA256 receipt first. Do not restore a different board's backup.
- If text or pointing fails, retain the fixture result; do not label BIOS or desktop compatibility proven.

Rebuild and verify:

```powershell
.\scripts\Build-Firmware.ps1
.\.venv\Scripts\python.exe -m pytest -q --junitxml=artifacts/tests.xml
.\.venv\Scripts\python.exe scripts/Smoke-Mcp.py
.\.venv\Scripts\python.exe scripts/Check-Usb-Descriptors.py
.\scripts\Flash-Device.ps1 -Port COM999 -CheckOnly
```

The toolchain is workspace-local: Arduino CLI 1.3.1, Espressif core 3.3.2, ArduinoJson 7.4.2. For this board, **`CDCOnBoot=cdc` means Disabled**. The published 0.2.1 firmware uses that setting and creates CDC explicitly only for `desktop`, before USB starts. The `USBMode=default` setting selects TinyUSB. PSRAM is disabled because this build does not need it.

See the [bench contract](bench-protocol.md) for protocol limits and the remaining physical checks. Return to the [README](../README.md) for console and MCP use.
