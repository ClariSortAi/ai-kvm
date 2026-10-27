#pragma once
#include <Arduino.h>
#include "esp32-hal-tinyusb.h"
// Internal key encoding: ASCII below 128, modifiers 128..135, usage+136 otherwise.
#define KEY_LEFT_CTRL 128
#define KEY_LEFT_SHIFT 129
#define KEY_LEFT_ALT 130
#define KEY_LEFT_GUI 131
#define KEY_RETURN (136+HID_KEY_ENTER)
#define KEY_ESC (136+HID_KEY_ESCAPE)
#define KEY_TAB (136+HID_KEY_TAB)
#define KEY_BACKSPACE (136+HID_KEY_BACKSPACE)
#define KEY_DELETE (136+HID_KEY_DELETE)
#define KEY_UP_ARROW (136+HID_KEY_ARROW_UP)
#define KEY_DOWN_ARROW (136+HID_KEY_ARROW_DOWN)
#define KEY_LEFT_ARROW (136+HID_KEY_ARROW_LEFT)
#define KEY_RIGHT_ARROW (136+HID_KEY_ARROW_RIGHT)
#define KEY_HOME (136+HID_KEY_HOME)
#define KEY_END (136+HID_KEY_END)
#define KEY_PAGE_UP (136+HID_KEY_PAGE_UP)
#define KEY_PAGE_DOWN (136+HID_KEY_PAGE_DOWN)
#define KEY_INSERT (136+HID_KEY_INSERT)
#define KEY_F1 (136+HID_KEY_F1)
#define KEY_F2 (136+HID_KEY_F2)
#define KEY_F3 (136+HID_KEY_F3)
#define KEY_F4 (136+HID_KEY_F4)
#define KEY_F5 (136+HID_KEY_F5)
#define KEY_F6 (136+HID_KEY_F6)
#define KEY_F7 (136+HID_KEY_F7)
#define KEY_F8 (136+HID_KEY_F8)
#define KEY_F9 (136+HID_KEY_F9)
#define KEY_F10 (136+HID_KEY_F10)
#define KEY_F11 (136+HID_KEY_F11)
#define KEY_F12 (136+HID_KEY_F12)
#define MOUSE_LEFT 1
#define MOUSE_RIGHT 2
#define MOUSE_MIDDLE 4

enum class UsbProfile : uint8_t { Desktop=0, Bios=1, BiosMouse=2 };
extern UsbProfile usbProfile;
extern bool hidFault;
extern uint8_t hostProtocol;
void hidBegin();
bool hidReady();
void hidClearFault();
void hidPollIdle();
struct BenchKeyboard {
  void begin() {}
  size_t press(uint8_t key);
  size_t release(uint8_t key);
  void releaseAll();
  size_t write(uint8_t key);
};
struct BenchMouse {
  void begin() {}
  void move(int8_t x, int8_t y, int8_t wheel=0);
  void press(uint8_t button);
  void release(uint8_t button);
  void click(uint8_t button);
};
struct BenchAbsolute { bool move(uint16_t x,uint16_t y); };
struct BenchHid { void begin() { hidBegin(); } bool ready() { return hidReady(); } };
extern BenchKeyboard Keyboard;
extern BenchMouse Mouse;
extern BenchAbsolute Absolute;
extern BenchHid Hid;
