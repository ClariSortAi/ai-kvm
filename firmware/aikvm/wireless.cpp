// The board connects OUT to its paired controller. TLS 1.2 PSK authenticates
// both peers without a clock, certificates, or an unauthenticated TCP listener.
#include "wireless.h"
#include <WiFi.h>
#include <NetworkClientSecure.h>
#include <Preferences.h>
#include <atomic>

constexpr size_t LINE_SIZE=1536;
struct Line { char text[LINE_SIZE+1]; };
struct Config { String ssid,password,host,identity,psk; uint16_t port=8787; };
static Config config;
static SemaphoreHandle_t configLock;
static QueueHandle_t incoming,outgoing;
static std::atomic<bool> online{false},restartLink{false},configured{false};
static std::atomic<uint32_t> generation{0};

static bool decode(JsonDocument &doc,Config &out,const char *deviceId=nullptr) {
  if (!doc["ssid"].is<const char *>() || !doc["password"].is<const char *>() ||
      !doc["host"].is<const char *>() || !doc["identity"].is<const char *>() || !doc["psk"].is<const char *>()) return false;
  out.ssid=doc["ssid"].as<String>(); out.password=doc["password"].as<String>();
  out.host=doc["host"].as<String>(); out.identity=doc["identity"].as<String>(); out.psk=doc["psk"].as<String>();
  int port=doc["port"] | 0;
  IPAddress address;
  if (!out.ssid.length() || out.ssid.length()>32 || out.password.length()<8 || out.password.length()>63 ||
      !address.fromString(out.host) || port<1024 || port>65535 || out.psk.length()!=64 || out.identity.length()>48) return false;
  if (deviceId && out.identity!=String("aikvm-")+deviceId) return false;
  for (char c:out.psk) if (!isxdigit(c)) return false;
  out.port=port;
  return true;
}
static void networkTask(void *) {
  NetworkClientSecure client;
  for (;;) {
    if (!configured.load()) { vTaskDelay(pdMS_TO_TICKS(100)); continue; }
    restartLink=false;
    Config current; uint32_t currentGeneration;
    xSemaphoreTake(configLock,portMAX_DELAY); current=config; currentGeneration=generation; xSemaphoreGive(configLock);
    WiFi.mode(WIFI_STA); WiFi.setSleep(false);
    WiFi.begin(current.ssid.c_str(),current.password.c_str());
    uint32_t began=millis();
    while (WiFi.status()!=WL_CONNECTED && uint32_t(millis()-began)<12000 && !restartLink && generation==currentGeneration) vTaskDelay(pdMS_TO_TICKS(100));
    if (WiFi.status()==WL_CONNECTED && !restartLink && generation==currentGeneration && configured) {
      client.setPreSharedKey(current.identity.c_str(),current.psk.c_str());
      client.setHandshakeTimeout(3); client.setTimeout(250);
      if (client.connect(current.host.c_str(),current.port,1500)) {
        online=true; client.setNoDelay(true);
        String input; input.reserve(LINE_SIZE); bool overflow=false;
        while (client.connected() && !restartLink && WiFi.status()==WL_CONNECTED && generation==currentGeneration && configured) {
          Line output;
          while (xQueueReceive(outgoing,&output,0)==pdTRUE) {
            size_t length=strlen(output.text);
            if (client.write((const uint8_t *)output.text,length)!=length || client.write('\n')!=1) { restartLink=true; break; }
          }
          for (unsigned count=0;count<256 && client.available();count++) {
            char c=client.read();
            if (c=='\n') {
              if (overflow) { restartLink=true; break; }
              if (input.length()) {
                Line line; input.toCharArray(line.text,sizeof(line.text));
                if (xQueueSend(incoming,&line,0)!=pdTRUE) { restartLink=true; break; }
              }
              input=""; overflow=false;
            } else if (c!='\r') {
              if (!c || input.length()>=LINE_SIZE) overflow=true;
              if (!overflow) input+=c;
            }
          }
          vTaskDelay(pdMS_TO_TICKS(2));
        }
      }
    }
    online=false; client.stop();
    xQueueReset(incoming); xQueueReset(outgoing);
    // A reconnect transports no old request and never rearms or replays input.
    vTaskDelay(pdMS_TO_TICKS(750));
  }
}
void wirelessBegin() {
  configLock=xSemaphoreCreateMutex();
  incoming=xQueueCreate(4,sizeof(Line)); outgoing=xQueueCreate(4,sizeof(Line));
  Preferences prefs; prefs.begin("aikvm",true); String stored=prefs.getString("wifi",""); prefs.end();
  JsonDocument doc;
  if (stored.length() && !deserializeJson(doc,stored) && decode(doc,config)) configured=true;
  xTaskCreatePinnedToCore(networkTask,"aikvm-tls",14336,nullptr,1,nullptr,0);
}
bool wirelessConfigured() { return configured; }
bool wirelessOnline() { return online; }
int wirelessRssi() { return WiFi.RSSI(); }
bool wirelessReceive(String &line) {
  Line input;
  if (xQueueReceive(incoming,&input,0)!=pdTRUE) return false;
  line=input.text; return true;
}
bool wirelessReply(const String &line) {
  if (line.length()>LINE_SIZE || !online) return false;
  Line output; line.toCharArray(output.text,sizeof(output.text));
  bool ok=xQueueSend(outgoing,&output,0)==pdTRUE;
  if (!ok) restartLink=true;
  return ok;
}
bool wirelessProvision(JsonDocument &doc,const char *deviceId) {
  Config next;
  if (!decode(doc,next,deviceId)) return false;
  JsonDocument stored;
  for (const char *key:{"ssid","password","host","identity","psk","port"}) stored[key]=doc[key];
  String encoded; serializeJson(stored,encoded);
  Preferences prefs;
  if (!prefs.begin("aikvm",false)) return false;
  bool ok=prefs.putString("wifi",encoded)==encoded.length(); prefs.end();
  if (!ok) return false;
  xSemaphoreTake(configLock,portMAX_DELAY); config=next; ++generation; xSemaphoreGive(configLock);
  configured=true; restartLink=true; return true;
}
void wirelessClear() {
  configured=false; restartLink=true;
  Preferences prefs; prefs.begin("aikvm",false); prefs.remove("wifi"); prefs.end();
  xSemaphoreTake(configLock,portMAX_DELAY); config=Config{}; ++generation; xSemaphoreGive(configLock);
}
void wirelessKick() { restartLink=true; }
