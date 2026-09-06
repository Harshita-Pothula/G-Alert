#include <HTTPClient.h>
#include <WiFi.h>
#include <time.h>

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";
const char* BACKEND_BASE_URL = "http://host.wokwi.internal:5000";
const char* REGION_KEY = "Tsho_Rolpa_Nepal";
const unsigned long SEND_INTERVAL_MS = 30000;

unsigned long sequence_number = 0;
unsigned long last_send_ms = 0;

bool connect_wifi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, 6);
  Serial.print("Connecting to Wokwi WiFi");
  for (int attempt = 0; WiFi.status() != WL_CONNECTED && attempt < 30; attempt++) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  return WiFi.status() == WL_CONNECTED;
}

bool synchronize_time() {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  struct tm time_info;
  Serial.print("Synchronizing UTC time with NTP");
  for (int attempt = 0; !getLocalTime(&time_info, 1000) && attempt < 30; attempt++) {
    Serial.print(".");
  }
  Serial.println();
  return getLocalTime(&time_info, 100);
}

bool utc_timestamp(char* buffer, size_t buffer_size) {
  struct tm time_info;
  if (!getLocalTime(&time_info, 1000)) {
    return false;
  }
  return strftime(buffer, buffer_size, "%Y-%m-%dT%H:%M:%SZ", &time_info) > 0;
}

bool send_telemetry(const char* sensor_id, const char* sensor_type,
                   float value, const char* unit) {
  char timestamp[25];
  if (!utc_timestamp(timestamp, sizeof(timestamp))) {
    Serial.println("Skipping telemetry: UTC timestamp unavailable");
    return false;
  }

  char payload[384];
  snprintf(
      payload, sizeof(payload),
      "{\"sensor_id\":\"%s\",\"region_key\":\"%s\",\"sensor_type\":\"%s\",\"timestamp\":\"%s\",\"reading\":{\"value\":%.2f,\"unit\":\"%s\"},\"sequence\":%lu,\"simulated\":true,\"provenance\":\"Wokwi ESP32 prototype telemetry\"}",
      sensor_id, REGION_KEY, sensor_type, timestamp, value, unit,
      sequence_number);

  HTTPClient http;
  String endpoint = String(BACKEND_BASE_URL) + "/api/sensors/telemetry";
  http.begin(endpoint);
  http.addHeader("Content-Type", "application/json");
  int status_code = http.POST((uint8_t*)payload, strlen(payload));
  Serial.printf("POST %s -> HTTP %d\n", endpoint.c_str(), status_code);
  Serial.println(payload);
  http.end();
  return status_code >= 200 && status_code < 300;
}

void send_sensor_batch() {
  sequence_number++;
  send_telemetry("WOKWI-VIB-001", "vibration", 4.20, "cm/s");
  send_telemetry("WOKWI-WATER-001", "water_level", 168.00, "cm");
  send_telemetry("WOKWI-RAIN-001", "rainfall", 12.50, "mm/h");
}

void setup() {
  Serial.begin(115200);
  delay(500);

  if (!connect_wifi()) {
    Serial.println("WiFi connection failed");
    return;
  }
  if (!synchronize_time()) {
    Serial.println("NTP synchronization failed");
    return;
  }

  send_sensor_batch();
  last_send_ms = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connect_wifi();
  }
  if (millis() - last_send_ms >= SEND_INTERVAL_MS) {
    send_sensor_batch();
    last_send_ms = millis();
  }
  delay(100);
}
