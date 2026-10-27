// One TinyUSB HID interface. BIOS profiles have no report IDs and no CDC.
#include "hid_driver.h"
#include "esp32-hal-tinyusb.h"

UsbProfile usbProfile=UsbProfile::Desktop;
bool hidFault=false;
uint8_t hostProtocol=HID_PROTOCOL_REPORT;
BenchKeyboard Keyboard;
BenchMouse Mouse;
BenchAbsolute Absolute;
BenchHid Hid;
static uint8_t keyboardReport[8]={0};
static uint8_t buttons=0;
static uint8_t keyboardLeds=0;
static uint8_t idleRate=0;
static uint32_t lastKeyboardSent=0;
static uint32_t lastMouseSent=0;
static uint8_t lastAbsolute[4]={0};
static uint8_t asciiKey(uint8_t key) {
  if (key>='a' && key<='z') return 4+key-'a';
  if (key>='A' && key<='Z') return (4+key-'A')|0x80;
  if (key>='1' && key<='9') return 30+key-'1';
  if (key=='0') return 39;
  if (key=='\n') return HID_KEY_ENTER;
  if (key=='\t') return HID_KEY_TAB;
  if (key==' ') return HID_KEY_SPACE;
  const char *digits="!@#$%^&*()";
  const char *found=strchr(digits,key);
  if (key && found) return (30+uint8_t(found-digits))|0x80;
  const char *plain="-=[]\\;'`,./";
  const char *shifted="_+{}|:\"~<>?";
  const uint8_t scans[]={45,46,47,48,49,51,52,53,54,55,56};
  found=strchr(plain,key);
  if (key && found) return scans[found-plain];
  found=strchr(shifted,key);
  if (key && found) return scans[found-shifted]|0x80;
  return 0;
}
static const uint8_t bootKeyboardDescriptor[]={TUD_HID_REPORT_DESC_KEYBOARD()};
static const uint8_t bootMouseDescriptor[]={TUD_HID_REPORT_DESC_MOUSE()};
static const uint8_t desktopDescriptor[]={
  TUD_HID_REPORT_DESC_KEYBOARD(HID_REPORT_ID(1)),
  TUD_HID_REPORT_DESC_MOUSE(HID_REPORT_ID(2)),
  0x05,0x01,0x09,0x02,0xA1,0x01,0x85,0x07,0x09,0x01,0xA1,0x00,
  0x09,0x30,0x09,0x31,0x15,0x00,0x26,0xFF,0x7F,0x75,0x10,0x95,0x02,0x81,0x02,0xC0,0xC0
};

static bool submit(uint8_t id,const void *data,uint16_t length) {
  uint32_t start=millis();
  while (!tud_hid_n_ready(0) && uint32_t(millis()-start)<60) delay(1);
  bool ok=tud_hid_n_ready(0) && tud_hid_n_report(0,id,data,length);
  if (!ok) hidFault=true;
  return ok;
}
static bool sendKeyboard() {
  if (usbProfile==UsbProfile::BiosMouse) { hidFault=true; return false; }
  lastKeyboardSent=millis();
  uint8_t id=(usbProfile==UsbProfile::Bios || hostProtocol==HID_PROTOCOL_BOOT)?0:1;
  return submit(id,keyboardReport,sizeof(keyboardReport));
}
static bool sendMouse(int8_t x=0,int8_t y=0,int8_t wheel=0) {
  if (usbProfile==UsbProfile::Bios || (usbProfile==UsbProfile::Desktop && hostProtocol==HID_PROTOCOL_BOOT)) {
    hidFault=true; return false;
  }
  uint8_t report[]={buttons,uint8_t(x),uint8_t(y),uint8_t(wheel),0};
  bool boot=usbProfile==UsbProfile::BiosMouse && hostProtocol==HID_PROTOCOL_BOOT;
  lastMouseSent=millis();
  return submit(usbProfile==UsbProfile::Desktop?2:0,report,boot?3:5);
}
static uint16_t descriptorLoader(uint8_t *dst,uint8_t *itf) {
  uint16_t reportSize=usbProfile==UsbProfile::Bios?sizeof(bootKeyboardDescriptor):
                      usbProfile==UsbProfile::BiosMouse?sizeof(bootMouseDescriptor):sizeof(desktopDescriptor);
  uint8_t endpoint=tinyusb_get_free_in_endpoint();
  if (!endpoint) return 0;
  uint8_t protocol=usbProfile==UsbProfile::BiosMouse?HID_ITF_PROTOCOL_MOUSE:HID_ITF_PROTOCOL_KEYBOARD;
  uint8_t descriptor[]={TUD_HID_DESCRIPTOR(*itf,0,protocol,reportSize,uint8_t(0x80|endpoint),16,1)};
  memcpy(dst,descriptor,sizeof(descriptor)); ++(*itf); return sizeof(descriptor);
}
void hidBegin() {
  tinyusb_enable_interface(USB_INTERFACE_HID,TUD_HID_DESC_LEN,descriptorLoader);
}
bool hidReady() { return tud_mounted(); }
void hidClearFault() { hidFault=false; }
// Called by main loop to honor a BIOS SET_IDLE request while keys are held.
void hidPollIdle() {
  if (usbProfile!=UsbProfile::BiosMouse && idleRate && hidReady() && uint32_t(millis()-lastKeyboardSent)>=uint32_t(idleRate)*4)
    sendKeyboard();
  if (usbProfile==UsbProfile::BiosMouse && idleRate && hidReady() && uint32_t(millis()-lastMouseSent)>=uint32_t(idleRate)*4)
    sendMouse();
}

size_t BenchKeyboard::press(uint8_t key) {
  if (usbProfile==UsbProfile::BiosMouse) { hidFault=true; return 0; }
  uint8_t scan=0;
  if (key>=136) scan=key-136;
  else if (key>=128) keyboardReport[0]|=1<<(key-128);
  else {
    uint8_t encoded=asciiKey(key);
    if (!encoded) return 0;
    if (encoded&0x80) keyboardReport[0]|=2;
    scan=encoded&0x7F;
  }
  if (scan) {
    bool found=false;
    for (uint8_t i=2;i<8;i++) if (keyboardReport[i]==scan) found=true;
    if (!found) {
      bool stored=false;
      for (uint8_t i=2;i<8;i++) if (!keyboardReport[i]) { keyboardReport[i]=scan; stored=true; break; }
      if (!stored) { hidFault=true; return 0; }
    }
  }
  return sendKeyboard()?1:0;
}
size_t BenchKeyboard::release(uint8_t key) {
  uint8_t scan=0;
  if (key>=136) scan=key-136;
  else if (key>=128) keyboardReport[0]&=~(1<<(key-128));
  else {
    uint8_t encoded=asciiKey(key);
    if (encoded&0x80) keyboardReport[0]&=~2;
    scan=encoded&0x7F;
  }
  for (uint8_t i=2;i<8;i++) if (scan && keyboardReport[i]==scan) keyboardReport[i]=0;
  return sendKeyboard()?1:0;
}
void BenchKeyboard::releaseAll() {
  memset(keyboardReport,0,sizeof(keyboardReport));
  if (usbProfile!=UsbProfile::BiosMouse && tud_mounted()) sendKeyboard();
}
size_t BenchKeyboard::write(uint8_t key) { size_t ok=press(key); release(key); return ok; }
void BenchMouse::move(int8_t x,int8_t y,int8_t wheel) { sendMouse(x,y,wheel); }
void BenchMouse::press(uint8_t button) { buttons|=button; sendMouse(); }
void BenchMouse::release(uint8_t button) {
  buttons&=~button;
  if (usbProfile!=UsbProfile::Bios && tud_mounted() && !(usbProfile==UsbProfile::Desktop && hostProtocol==HID_PROTOCOL_BOOT)) sendMouse();
}
void BenchMouse::click(uint8_t button) { press(button); release(button); }
bool BenchAbsolute::move(uint16_t x,uint16_t y) {
  if (usbProfile!=UsbProfile::Desktop || hostProtocol==HID_PROTOCOL_BOOT) { hidFault=true; return false; }
  uint8_t report[]={uint8_t(x),uint8_t(x>>8),uint8_t(y),uint8_t(y>>8)};
  memcpy(lastAbsolute,report,sizeof(report));
  return submit(7,report,sizeof(report));
}

extern "C" {
uint8_t const *tud_hid_descriptor_report_cb(uint8_t instance) {
  return usbProfile==UsbProfile::Bios?bootKeyboardDescriptor:usbProfile==UsbProfile::BiosMouse?bootMouseDescriptor:desktopDescriptor;
}
void tud_hid_set_protocol_cb(uint8_t instance,uint8_t protocol) { hostProtocol=protocol; }
bool tud_hid_set_idle_cb(uint8_t instance,uint8_t rate) { idleRate=rate; return true; }
uint16_t tud_hid_get_report_cb(uint8_t instance,uint8_t id,hid_report_type_t type,uint8_t *buffer,uint16_t reqlen) {
  if (type==HID_REPORT_TYPE_INPUT && usbProfile!=UsbProfile::BiosMouse && (id==0 || id==1)) {
    uint16_t length=min(reqlen,uint16_t(sizeof(keyboardReport))); memcpy(buffer,keyboardReport,length); return length;
  }
  if (type==HID_REPORT_TYPE_INPUT && ((usbProfile==UsbProfile::BiosMouse && id==0) || (usbProfile==UsbProfile::Desktop && id==2))) {
    uint8_t report[]={buttons,0,0,0,0};
    uint16_t size=usbProfile==UsbProfile::BiosMouse && hostProtocol==HID_PROTOCOL_BOOT?3:5;
    uint16_t length=min(reqlen,size); memcpy(buffer,report,length); return length;
  }
  if (type==HID_REPORT_TYPE_INPUT && usbProfile==UsbProfile::Desktop && id==7) {
    uint16_t length=min(reqlen,uint16_t(sizeof(lastAbsolute))); memcpy(buffer,lastAbsolute,length); return length;
  }
  if (type==HID_REPORT_TYPE_OUTPUT && reqlen) { buffer[0]=keyboardLeds; return 1; }
  return 0;
}
void tud_hid_set_report_cb(uint8_t instance,uint8_t id,hid_report_type_t type,uint8_t const *buffer,uint16_t size) {
  if (type==HID_REPORT_TYPE_OUTPUT && size) keyboardLeds=buffer[0];
}
}
