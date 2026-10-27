# Dependencies

The bench uses the following third-party components. Their complete notices are in the locally installed packages/toolchain; retain applicable notices with any redistributed binaries. This inventory is preparation evidence, not a completed commercial distribution review.

| Component | Pinned version | Upstream license reference |
|---|---|---|
| Arduino CLI (build tool) | 1.3.1 | [GPL-3.0](https://github.com/arduino/arduino-cli/blob/v1.3.1/LICENSE.txt) |
| Arduino ESP32 core / USB library | 3.3.2 | [Core LGPL-2.1, file-specific notices including Apache-2.0 USB files](https://github.com/espressif/arduino-esp32/blob/3.3.2/LICENSE.md) |
| ESP-IDF and included SDK components | Bundled with core | [ESP-IDF licensing and subcomponent notices](https://github.com/espressif/esp-idf/blob/v5.5.1/LICENSE) |
| TinyUSB | Bundled with core | [MIT](https://github.com/hathach/tinyusb/blob/master/LICENSE) |
| ArduinoJson | 7.4.2 | [MIT](https://github.com/bblanchon/ArduinoJson/blob/v7.4.2/LICENSE.txt) |
| MCP Python SDK | 2.3.0 | [MIT](https://github.com/modelcontextprotocol/python-sdk/blob/main/LICENSE) |
| pyserial | 3.5 | [BSD](https://github.com/pyserial/pyserial/blob/v3.5/LICENSE.txt) |
| mss | 10.1.0 | [MIT](https://github.com/BoboTiG/python-mss/blob/main/LICENSE.txt) |
| Pillow | 12.0.0 | [HPND and bundled notices](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| OpenCV Python | 4.13.0.92 | [OpenCV and binary dependency notices](https://github.com/opencv/opencv-python/blob/master/LICENSE.txt) |

Python transitive package versions are recorded in `requirements.lock.txt`. No `esp32-iphone-agent` or AirPlay sources were incorporated. This project's own code is MIT licensed (see `LICENSE`). Third-party code linked into the firmware images is listed in `NOTICES.md`.
