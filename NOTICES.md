# Third-party notices

The firmware images in `artifacts/firmware/` statically link the components below. Versions are pinned in `artifacts/firmware-manifest.json`, `arduino-cli.yaml` and `THIRD_PARTY.md`. The project's own code is MIT (see `LICENSE`).

| Component | Version | License | License text |
|---|---|---|---|
| Arduino-ESP32 core (Espressif) | 3.3.2 | LGPL-2.1 (file-specific notices, some Apache-2.0) | https://github.com/espressif/arduino-esp32/blob/3.3.2/LICENSE.md |
| ESP-IDF and SDK components (bundled with the core) | v5.5.1 | Apache-2.0 (subcomponents carry their own notices) | https://github.com/espressif/esp-idf/blob/v5.5.1/LICENSE |
| TinyUSB (bundled with the core) | as bundled with core 3.3.2 | MIT | https://github.com/hathach/tinyusb/blob/master/LICENSE |
| ArduinoJson (Benoit Blanchon) | 7.4.2 | MIT | https://github.com/bblanchon/ArduinoJson/blob/v7.4.2/LICENSE.txt |

Canonical license texts: LGPL-2.1 https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt, Apache-2.0 https://www.apache.org/licenses/LICENSE-2.0.txt, MIT https://opensource.org/license/mit.

## LGPL-2.1 note (Arduino-ESP32 core)

The complete source of this project is in this repository, and the firmware rebuilds with `arduino-cli` as documented in `README.md` (`scripts/Build-Firmware.ps1`, `arduino-cli.yaml`). You can replace the Arduino-ESP32 core with a modified version and relink: install your modified core in the arduino-cli data directory, rebuild, and flash the new images with `scripts/Flash-Device.ps1`.

## Build and host tools (not linked into the firmware)

Arduino CLI 1.3.1 (GPL-3.0) is used only as a build tool. Python dependencies of the controller are listed in `THIRD_PARTY.md` and `requirements.lock.txt`.
