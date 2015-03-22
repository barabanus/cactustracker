/////////////////////////////////////////////////////////////////////////////////////////////////
// Cactus Tracker v1.0.9 / March 22, 2015
// by Maksym Ganenko <buratin.barabanus at Google Mail>
/////////////////////////////////////////////////////////////////////////////////////////////////

#include <dht.h>

const int PIN_LM35    = A4;
const int PIN_DHT22   = 13;
const int PIN_HEATER  = 10;
const int PIN_LIGHT   = 2;

const int DELAY_MS    = 1000;
const int MAGIC       = 10101;
const float TEMP_MAX  = 40.0;

/////////////////////////////////////////////////////////////////////////////////////////////////

struct SmoothValue    {
  float value;
  SmoothValue() : value(NAN)  { }
  bool valid()                { return !isnan(value); }
  void update(float aValue)   { value = isnan(value) ? aValue : value * 0.95f + aValue * 0.05f; }
};

/////////////////////////////////////////////////////////////////////////////////////////////////

enum { OFF = 0, ON, AUTO };

int mode              = AUTO;
bool heater           = false;
bool light            = false;
float heaterFrom      = 5.f;
float heaterTo        = 10.f;

SmoothValue tempLM35, tempDHT22, humidityDHT22;
dht dhtReader;

/////////////////////////////////////////////////////////////////////////////////////////////////

void startHeater() {
  digitalWrite(PIN_HEATER, HIGH);
  heater = true;
}

void stopHeater() {
  digitalWrite(PIN_HEATER, LOW);
  heater = false;
}

void startLight() {
  digitalWrite(PIN_LIGHT, HIGH);
  light = true;
}

void stopLight() {
  digitalWrite(PIN_LIGHT, LOW);
  light = false;
}

/////////////////////////////////////////////////////////////////////////////////////////////////

void setup() {
  Serial.begin(115200);
  digitalWrite(PIN_HEATER, LOW);
  pinMode(PIN_HEATER, OUTPUT);

  digitalWrite(PIN_LIGHT, LOW);
  pinMode(PIN_LIGHT, OUTPUT);

  analogReference(INTERNAL);
  for (int i = 0; i < 100; ++i) {
    analogRead(PIN_LM35);
  }
}

void loop() {
  float temp = float(analogRead(PIN_LM35)) / 1024 * 1.1 / 10e-3;
  tempLM35.update(temp);
  
  int code = dhtReader.read22(PIN_DHT22);
  if (code == DHTLIB_OK) {
    tempDHT22.update(dhtReader.temperature);
    humidityDHT22.update(dhtReader.humidity);    
  }
  
  if (Serial.available()) {
    if (Serial.parseInt() == MAGIC) {
      int newMode = Serial.parseInt();
      float newHeaterFrom = Serial.parseFloat();
      float newHeaterTo = Serial.parseFloat();
      int newLight = Serial.parseInt();
      
      if (newMode >= OFF && newMode <= AUTO && newHeaterFrom < newHeaterTo) {
        mode = newMode;
        heaterFrom = newHeaterFrom;
        heaterTo = newHeaterTo;
        stopHeater();
      }

      if (newLight) startLight();
      else          stopLight();
    }
  }
  
  bool overheat = tempLM35.value >= TEMP_MAX;
  if (!overheat && (mode == ON || (mode == AUTO && tempLM35.value <= heaterFrom))) {
    startHeater();
  }
  if (overheat || mode == OFF || (mode == AUTO && tempLM35.value >= heaterTo)) {
    stopHeater();
  }
  
  Serial.print("mode = ");            Serial.print(mode);
  Serial.print(", tempLM35 = ");      Serial.print(tempLM35.value);
  Serial.print(", tempDHT22 = ");     Serial.print(tempDHT22.value);
  Serial.print(", humidityDHT22 = "); Serial.print(humidityDHT22.value);
  Serial.print(", heater = ");        Serial.print(heater);
  Serial.print(", heaterFrom = ");    Serial.print(heaterFrom);
  Serial.print(", heaterTo = ");      Serial.print(heaterTo);
  Serial.print(", light = ");         Serial.println(light);
  
  delay(DELAY_MS);
}

/////////////////////////////////////////////////////////////////////////////////////////////////
