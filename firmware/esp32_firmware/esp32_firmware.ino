/*
 * Smart Organic Manure Analysis - ESP32 Telemetry Firmware
 * SIH1767 – GOBARdhan System
 * 
 * Sensors:
 * - DS18B20 Digital Temperature Sensor on GPIO 4 (with 4.7k pull-up resistor)
 * - Resistive Soil Moisture Probe on GPIO 34 (ADC1_CHANNEL_6)
 * 
 * Transmission:
 * - Sends JSON payload via HTTP POST (plain HTTP, not HTTPS) to /api/readings/ingest every 60 seconds
 * - Header: X-Device-Key with provisioned device key
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ================= CONFIGURATION CONSTANTS =================
// Replace with your real Wi-Fi network credentials
const char* WIFI_SSID     = "My123";
const char* WIFI_PASSWORD = "77777777";

// Local server URL where FastAPI ingest_api is running (HTTP connection to laptop address)
const char* SERVER_URL    = "http://10.141.140.200:8000/api/readings/ingest";

// Unique Device Key generated during farmer device registration in the web portal
const char* DEVICE_API_KEY = "DEV_3_09c91c584e6fc51d8508a56e14e5af8f";

// Sensor Pin Definitions
const int ONE_WIRE_BUS_PIN  = 4;   // DS18B20 Data Pin (GPIO 4)
const int MOISTURE_ADC_PIN  = 34;  // Resistive Soil Moisture Probe Analog Pin (GPIO 34)

// Calibration Constants for Resistive Soil Moisture Probe
// In dry air/soil (high resistance): raw ADC is high (~3500)
// In water/saturated compost (low resistance): raw ADC is low (~1200)
const int ADC_DRY = 4095; // Raw ADC reading in dry compost/air (0% moisture)
const int ADC_WET = 1200; // Raw ADC reading in water/saturated compost (100% moisture)

// Transmission Interval
const unsigned long SEND_INTERVAL_MS = 60000; // 60 seconds
unsigned long lastSendTime = 0;

// OneWire & DallasTemperature instances
OneWire oneWire(ONE_WIRE_BUS_PIN);
DallasTemperature tempSensors(&oneWire);

// Connect or reconnect to Wi-Fi
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  Serial.print("[WiFi] Connecting to: ");
  Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected successfully!");
    Serial.print("[WiFi] IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] Connection failed. Will retry on next loop.");
  }
}

// Read DS18B20 Temperature
float readTemperature() {
  tempSensors.requestTemperatures();
  float tempC = tempSensors.getTempCByIndex(0);
  if (tempC == DEVICE_DISCONNECTED_C) {
    Serial.println("[Sensor Error] DS18B20 disconnected or pull-up missing!");
    return -999.0;
  }
  return tempC;
}

// Read Resistive Soil Moisture Probe raw ADC value
int readMoistureRawADC() {
  int rawValue = analogRead(MOISTURE_ADC_PIN);
  return rawValue;
}

// Calculate moisture percentage from resistive probe raw ADC
float calculateMoisturePercent(int rawValue) {
  // Constrain reading to calibration range
  int constrainedVal = constrain(rawValue, ADC_WET, ADC_DRY);
  
  // Map raw ADC inversely to percentage for resistive probe (Dry = 0%, Wet = 100%)
  float moisture = map(constrainedVal, ADC_DRY, ADC_WET, 0, 100);
  
  Serial.printf("[Sensor] Resistive Probe Raw ADC: %d, Calculated Moisture: %.1f%%\n", rawValue, moisture);
  return moisture;
}

// Send Telemetry Reading via HTTP POST (plain HTTP)
void sendTelemetry(float temperature, float moisturePercent, int rawAdc) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[HTTP] Wi-Fi not connected. Attempting reconnection...");
    connectWiFi();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[HTTP] Aborted transmission: No Wi-Fi link.");
      return;
    }
  }

  HTTPClient http;
  http.begin(SERVER_URL); // Plain HTTP connection to laptop address
  http.setTimeout(10000); // 10s timeout
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_API_KEY);

  // Construct JSON Payload matching ingest_api.py schema
  String payload = "{\"temperature_c\": " + String(temperature, 2) + 
                   ", \"moisture_percent\": " + String(moisturePercent, 2) +
                   ", \"moisture_raw_adc\": " + String(rawAdc) + "}";

  Serial.println("[HTTP] Posting telemetry to laptop: " + payload);
  int httpResponseCode = http.POST(payload);

  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.printf("[HTTP] Server Response Status: %d\n", httpResponseCode);
    Serial.println("[HTTP] Server Response Body: " + response);
  } else {
    Serial.printf("[HTTP Error] POST failed, error: %s\n", http.errorToString(httpResponseCode).c_str());
  }

  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== GOBARdhan Smart Manure Telemetry Node Starting ===");
  Serial.println("[Sensor Setup] Initializing DS18B20 and Resistive Moisture Probe");

  // Initialize sensors
  tempSensors.begin();
  analogReadResolution(12); // ESP32 12-bit ADC (0 - 4095)
  analogSetAttenuation(ADC_11db); // Full range 0 - 3.3V

  // Initialize Wi-Fi
  connectWiFi();
}

void loop() {
  unsigned long currentMillis = millis();

  // Send reading every 60 seconds
  if (currentMillis - lastSendTime >= SEND_INTERVAL_MS || lastSendTime == 0) {
    lastSendTime = currentMillis;

    float temp = readTemperature();
    int rawAdc = readMoistureRawADC();
    float moisture = calculateMoisturePercent(rawAdc);

    // Validate sensor reading bounds before sending
    if (temp >= -10.0 && temp <= 80.0 && moisture >= 0.0 && moisture <= 100.0) {
      sendTelemetry(temp, moisture, rawAdc);
    } else {
      Serial.printf("[Validation Failed] Sensor values out of range: Temp=%.2f C, ADC=%d, Moist=%.2f %%\n", temp, rawAdc, moisture);
    }
  }

  delay(100);
}
