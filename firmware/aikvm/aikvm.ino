// AI KVM: USB setup, paired outbound TLS and explicit desktop/BIOS USB profiles.
#include <Arduino.h>
#include <ArduinoJson.h>
#include "USB.h"
#include "USBCDC.h"
#include <Preferences.h>
#include "hid_driver.h"
#include "wireless.h"

#if ARDUINO_USB_MODE != 0 || ARDUINO_USB_CDC_ON_BOOT
#error Build XIAO_ESP32S3 with USBMode=default and CDCOnBoot=cdc (Disabled; CDC is explicit)
#endif
USBCDC *console=nullptr;
enum class Source { None, Usb, Wireless };
Source source=Source::None,owner=Source::None;

constexpr uint32_t LEASE_MS = 2000;
constexpr size_t MAX_LINE = 1536;
char session[17] = "";
char deviceId[17];
bool armed = false;
uint32_t lastAlive = 0, lastSeq = 0;
uint32_t holdStarted = 0;
bool heldInput = false;
uint32_t leaseReleases=0,disconnectReleases=0,holdReleases=0;
String input, lastRequest, lastReply;
bool overflow = false;

void releaseInputs() {
  Keyboard.releaseAll();
  Mouse.release(MOUSE_LEFT | MOUSE_RIGHT | MOUSE_MIDDLE);
  heldInput = false;
}
void disarm() { releaseInputs(); armed = false; session[0] = 0; owner=Source::None; }
void output(const String &line) {
  if (source==Source::Usb && console) console->println(line);
  else if (source==Source::Wireless && !wirelessReply(line)) disarm();
}
void reply(JsonDocument &doc) { String line; serializeJson(doc,line); output(line); }
const char *profileName() { return usbProfile==UsbProfile::Bios?"bios":usbProfile==UsbProfile::BiosMouse?"bios_mouse":"desktop"; }
void error(const char *message, uint32_t seq = 0) {
  JsonDocument out; out["ok"] = false; out["error"] = message; out["seq"] = seq; reply(out);
}
uint8_t keyCode(const char *name) {
  if (!name) return 0;
  if (strlen(name) == 1 && name[0] >= 32 && name[0] <= 126) return name[0];
  struct Entry { const char *name; uint8_t code; };
  static const Entry keys[] = {
    {"CTRL",KEY_LEFT_CTRL},{"SHIFT",KEY_LEFT_SHIFT},{"ALT",KEY_LEFT_ALT},{"GUI",KEY_LEFT_GUI},
    {"ENTER",KEY_RETURN},{"ESC",KEY_ESC},{"TAB",KEY_TAB},{"BACKSPACE",KEY_BACKSPACE},
    {"DELETE",KEY_DELETE},{"UP",KEY_UP_ARROW},{"DOWN",KEY_DOWN_ARROW},
    {"LEFT",KEY_LEFT_ARROW},{"RIGHT",KEY_RIGHT_ARROW},{"HOME",KEY_HOME},{"END",KEY_END},
    {"PAGEUP",KEY_PAGE_UP},{"PAGEDOWN",KEY_PAGE_DOWN},{"INSERT",KEY_INSERT},
    {"F1",KEY_F1},{"F2",KEY_F2},{"F3",KEY_F3},{"F4",KEY_F4},{"F5",KEY_F5},
    {"F6",KEY_F6},{"F7",KEY_F7},{"F8",KEY_F8},{"F9",KEY_F9},{"F10",KEY_F10},
    {"F11",KEY_F11},{"F12",KEY_F12},{"SPACE",' '}
  };
  for (auto &key : keys) if (!strcmp(name, key.name)) return key.code;
  return 0;
}
bool integer(JsonDocument &doc, const char *field, int low, int high) {
  return doc[field].is<int>() && doc[field].as<int>() >= low && doc[field].as<int>() <= high;
}

void command(const String &line) {
  JsonDocument doc;
  if (deserializeJson(doc, line) || !doc.is<JsonObject>()) { error("invalid_json"); return; }
  const char *op = doc["op"] | "";
  if (!doc["v"].is<int>() || doc["v"].as<int>() != 1) { error("protocol_version"); return; }
  if (!strcmp(op,"provision") || !strcmp(op,"clear_pairing")) {
    if (source!=Source::Usb || armed) { error("physical_usb_disarmed_required"); return; }
    bool ok=true;
    if (!strcmp(op,"provision")) ok=wirelessProvision(doc,deviceId); else wirelessClear();
    JsonDocument out; out["ok"]=ok;
    if (!ok) out["error"]="invalid_provisioning_or_storage_failed";
    else out["state"]=!strcmp(op,"provision")?"paired":"unpaired";
    reply(out); return;
  }
  if (!strcmp(op, "stop")) {
    disarm(); JsonDocument out; out["ok"] = true; out["state"] = "disarmed";
    out["hid_ready"] = Hid.ready(); reply(out); return;
  }
  if (!strcmp(op, "hello")) {
    if (armed && owner!=source) { error("controller_busy"); return; }
    disarm(); lastSeq = 0; lastRequest = ""; lastReply = "";
    owner=source;
    snprintf(session, sizeof(session), "%08lx%08lx", (unsigned long)esp_random(), (unsigned long)esp_random());
    JsonDocument out; out["ok"] = true; out["session"] = session;
    out["device_id"] = deviceId; out["firmware"] = "0.2.1";
    out["protocol"] = 1; out["lease_ms"] = LEASE_MS; out["hid_ready"] = Hid.ready();
    out["armed"] = false; out["transport"] = source==Source::Usb?"usb-cdc":"tls-psk";
    out["usb_profile"]=profileName(); out["host_protocol"]=hostProtocol==0?"boot":"report";
    out["keyboard_report_bytes"]=usbProfile==UsbProfile::BiosMouse?0:8;
    out["mouse_report_bytes"]=usbProfile==UsbProfile::Bios?0:(usbProfile==UsbProfile::BiosMouse && hostProtocol==0?3:5);
    out["absolute_pointer"]=usbProfile==UsbProfile::Desktop && hostProtocol!=0;
    out["usb_cdc"]=usbProfile==UsbProfile::Desktop; out["wireless_configured"]=wirelessConfigured();
    out["wireless_online"]=wirelessOnline(); out["lease_releases"]=leaseReleases;
    if (wirelessOnline()) out["wifi_rssi_dbm"] = wirelessRssi();
    out["disconnect_releases"]=disconnectReleases; out["hold_releases"]=holdReleases;
    reply(out); return;
  }
  if (owner!=source || !session[0] || strcmp(doc["session"] | "", session)) { error("invalid_session"); return; }
  if (!strcmp(op,"profile")) {
    const char *profile=doc["profile"] | "";
    int selected=!strcmp(profile,"desktop")?0:!strcmp(profile,"bios")?1:!strcmp(profile,"bios_mouse")?2:-1;
    if (armed || selected<0 || (selected!=0 && !wirelessConfigured())) { error("disarm_and_pair_before_profile_change"); return; }
    Preferences prefs; prefs.begin("aikvm",false); bool ok=prefs.putUChar("profile",selected)==1; prefs.end();
    JsonDocument out; out["ok"]=ok; out["next_usb_profile"]=profile; out["reconnect_usb_required"]=true; reply(out); return;
  }
  if (!strcmp(op, "ping")) {
    if (armed) lastAlive = millis();
    JsonDocument out; out["ok"] = true; out["armed"] = armed;
    out["host_protocol"]=hostProtocol==0?"boot":"report";
    out["hid_ready"] = Hid.ready();
    if (wirelessOnline()) out["wifi_rssi_dbm"] = wirelessRssi();
    reply(out); return;
  }
  if (!doc["seq"].is<uint32_t>() || !doc["seq"].as<uint32_t>()) { error("invalid_sequence"); return; }
  uint32_t seq = doc["seq"];
  if (seq == lastSeq) {
    if (line == lastRequest) output(lastReply);
    else error("sequence_payload_conflict", seq);
    return;
  }
  if (seq != lastSeq + 1) { error("out_of_order", seq); return; }
  // Consume even rejected sequenced requests. Cache the exact result for duplicates.
  lastSeq = seq; lastRequest = line;
  JsonDocument out; out["seq"] = seq; out["ok"] = false;
  bool valid = true;
  if (!strcmp(op, "arm")) {
    if (!Hid.ready()) out["error"] = "hid_not_ready";
    else { releaseInputs(); armed = true; lastAlive = millis(); out["ok"] = true; out["state"] = "armed"; }
  } else if (!armed) out["error"] = "not_armed";
  else if (!Hid.ready()) { disarm(); out["error"] = "hid_not_ready"; }
  else {
    hidClearFault();
    if (!strcmp(op, "type")) {
      const char *text = doc["text"].is<const char *>() ? doc["text"].as<const char *>() : nullptr;
      valid = text && strlen(text) == 1 && ((text[0] >= 32 && text[0] <= 126) || text[0] == '\n' || text[0] == '\t');
      if (valid) { Keyboard.releaseAll(); Keyboard.write(text[0]); Keyboard.releaseAll(); }
    } else if (!strcmp(op, "press")) {
      JsonArray keys = doc["keys"].as<JsonArray>();
      valid = !keys.isNull() && keys.size() > 0 && keys.size() <= 6;
      for (JsonVariant key : keys) if (!key.is<const char *>() || !keyCode(key.as<const char *>())) valid = false;
      if (valid) {
        Keyboard.releaseAll();
        for (JsonVariant key : keys) Keyboard.press(keyCode(key.as<const char *>()));
        delay(10); Keyboard.releaseAll();
      }
    } else if (!strcmp(op, "key_down") || !strcmp(op, "key_up")) {
      uint8_t key = keyCode(doc["key"] | ""); valid = key != 0;
      if (valid) {
        if (!strcmp(op, "key_down")) { Keyboard.press(key); if (!heldInput) holdStarted=millis(); heldInput=true; }
        else Keyboard.release(key);
      }
    } else if (!strcmp(op, "move")) {
      valid = integer(doc,"dx",-127,127) && integer(doc,"dy",-127,127);
      if (valid) Mouse.move(doc["dx"], doc["dy"]);
    } else if (!strcmp(op, "move_abs")) {
      valid = integer(doc,"x",0,32767) && integer(doc,"y",0,32767);
      if (valid && !Absolute.move(doc["x"], doc["y"])) { valid = false; out["error"] = "hid_send_failed"; }
    } else if (!strcmp(op, "click") || !strcmp(op, "button_down") || !strcmp(op, "button_up")) {
      const char *button = doc["button"] | "";
      uint8_t code = !strcmp(button,"left") ? MOUSE_LEFT : !strcmp(button,"right") ? MOUSE_RIGHT : !strcmp(button,"middle") ? MOUSE_MIDDLE : 0;
      valid = code != 0;
      if (valid) {
        if (!strcmp(op,"click")) Mouse.click(code);
        else if (!strcmp(op,"button_down")) { Mouse.press(code); if (!heldInput) holdStarted=millis(); heldInput=true; }
        else Mouse.release(code);
      }
    } else if (!strcmp(op,"scroll")) {
      valid = integer(doc,"ticks",-127,127); if (valid) Mouse.move(0,0,doc["ticks"]);
    } else if (!strcmp(op,"release")) releaseInputs();
    else valid = false;
    if (valid && hidFault) { valid=false; out["error"]="hid_send_failed_or_profile_unsupported"; disarm(); }
    if (valid) { out["ok"] = true; out["state"] = "hid_submitted"; lastAlive = millis(); }
    else if (out["error"].isNull()) out["error"] = "invalid_operation_or_arguments";
  }
  lastReply = ""; serializeJson(out,lastReply); output(lastReply);
}

void setup() {
  snprintf(deviceId,sizeof(deviceId),"%012llx",ESP.getEfuseMac());
  Preferences prefs; prefs.begin("aikvm",true); uint8_t selected=prefs.getUChar("profile",0); prefs.end();
  usbProfile=selected<=2?UsbProfile(selected):UsbProfile::Desktop;
  input.reserve(MAX_LINE); lastRequest.reserve(MAX_LINE);
  Keyboard.begin(); Mouse.begin(); Hid.begin();
  if (usbProfile==UsbProfile::Desktop) { console=new USBCDC(); console->setRxBufferSize(MAX_LINE+1); console->begin(115200); }
  USB.productName(usbProfile==UsbProfile::Desktop?"AI KVM":"AI KVM BIOS"); USB.serialNumber(deviceId);
  USB.usbClass(0); USB.usbSubClass(0); USB.usbProtocol(0);
  USB.begin(); wirelessBegin();
}
void loop() {
  if (heldInput && uint32_t(millis()-holdStarted) > 1500) { ++holdReleases; releaseInputs(); }
  bool disconnected=(owner==Source::Usb && (!console || !(*console))) || (owner==Source::Wireless && !wirelessOnline());
  if (owner!=Source::None && disconnected) { if (armed) ++disconnectReleases; disarm(); }
  if (armed && uint32_t(millis()-lastAlive) > LEASE_MS) { ++leaseReleases; disarm(); }
  if (armed && !Hid.ready()) disarm();
  // Bound work per loop so an endless incoming stream cannot starve the lease.
  for (unsigned n=0; n<128 && console && console->available(); n++) {
    char c=console->read(); source=Source::Usb;
    if (c=='\n') {
      if (overflow) error("line_too_long"); else if (input.length()) command(input);
      input=""; overflow=false;
    } else if (c!='\r') {
      if (input.length()<MAX_LINE && !overflow) input+=c;
      else { overflow=true; input=""; }
    }
  }
  String wirelessLine;
  if (wirelessReceive(wirelessLine)) { source=Source::Wireless; command(wirelessLine); }
  hidPollIdle();
  delay(1);
}
