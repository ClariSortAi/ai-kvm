#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>
bool wirelessConfigured();
bool wirelessOnline();
bool wirelessReceive(String &line);
bool wirelessReply(const String &line);
void wirelessBegin();
bool wirelessProvision(JsonDocument &doc,const char *deviceId);
void wirelessClear();
void wirelessKick();
