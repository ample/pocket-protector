#include <Arduino.h>

// ESP32-C3 Super Mini -> Raspberry Pi recorder controller
//
// Wiring:
//   GPIO 4 -> momentary button -> common GND
//   GPIO 5 -> 1K resistor -> base of 2N2222 controlling PowerBoost K
//   GPIO 3 -> Raspberry Pi physical pin 10 (GPIO15)
//   ESP32 GND -> common ground
//
// Behavior:
//   Single click -> short LOW pulse to Pi = RECORD_TOGGLE
//   Triple click -> one K tap = turn PowerBoost/Pi on
//   Long press   -> tell Pi to shut down, wait, then DOUBLE-TAP K
//                   to turn the PowerBoost 5V output off
//
// GPIO3 is open-drain so the always-on ESP32 does NOT drive voltage
// into the Raspberry Pi while the Pi is powered off.

const int BUTTON_PIN = 4;
const int K_PIN = 5;
const int PI_SIGNAL_PIN = 3;

const unsigned long DEBOUNCE_MS = 40;
const unsigned long CLICK_WINDOW_MS = 600;
const unsigned long LONG_PRESS_MS = 2500;

// K-button timing
// The FM5324HJ1 recognizes a short press as a tap and a double press
// as "turn boost output off."
const unsigned long K_TAP_MS = 100;
const unsigned long K_DOUBLE_GAP_MS = 150;

// Pulse lengths sent to Raspberry Pi
const unsigned long RECORD_PULSE_MS = 150;
const unsigned long SHUTDOWN_PULSE_MS = 1200;

// Give Linux time to finish shutting down before removing 5V.
const unsigned long SHUTDOWN_CUT_DELAY_MS = 15000;

bool buttonWasDown = false;
unsigned long buttonDownAt = 0;

int clickCount = 0;
unsigned long lastClickAt = 0;


void setKPressed(bool pressed) {
  // GPIO5 HIGH turns on the NPN transistor,
  // which pulls the PowerBoost K pin to common ground.
  digitalWrite(K_PIN, pressed ? HIGH : LOW);
}


void tapK() {
  Serial.println("Tapping PowerBoost K...");

  setKPressed(true);
  delay(K_TAP_MS);
  setKPressed(false);

  Serial.println("K tap complete.");
}


void doubleTapK() {
  Serial.println("Double-tapping PowerBoost K to turn 5V off...");

  setKPressed(true);
  delay(K_TAP_MS);
  setKPressed(false);

  delay(K_DOUBLE_GAP_MS);

  setKPressed(true);
  delay(K_TAP_MS);
  setKPressed(false);

  Serial.println("K double-tap complete.");
}


void signalPi(unsigned long pulseLengthMs) {
  // Open-drain line: LOW actively pulls the Pi input to ground.
  // HIGH releases the line so the Pi's own pull-up holds it high.
  digitalWrite(PI_SIGNAL_PIN, LOW);
  delay(pulseLengthMs);
  digitalWrite(PI_SIGNAL_PIN, HIGH);
}


void shutdownPiAndCutPower() {
  Serial.println("Sending shutdown request to Pi...");
  signalPi(SHUTDOWN_PULSE_MS);

  Serial.println("Waiting for Raspberry Pi to shut down...");
  delay(SHUTDOWN_CUT_DELAY_MS);

  // FM5324HJ1: double press on K disables boost output.
  doubleTapK();
}


void setup() {
  Serial.begin(115200);

  pinMode(BUTTON_PIN, INPUT_PULLUP);

  pinMode(K_PIN, OUTPUT);
  setKPressed(false);

  pinMode(PI_SIGNAL_PIN, OUTPUT_OPEN_DRAIN);
  digitalWrite(PI_SIGNAL_PIN, HIGH);  // release line

  delay(300);

  Serial.println();
  Serial.println("ESP32 recorder controller started.");
  Serial.println("Single click = record toggle");
  Serial.println("Triple click = PowerBoost ON");
  Serial.println("Long press   = shutdown Pi, then PowerBoost OFF");
}


void loop() {
  bool buttonDown = (digitalRead(BUTTON_PIN) == LOW);

  if (buttonDown && !buttonWasDown) {
    buttonDownAt = millis();
    buttonWasDown = true;
    delay(DEBOUNCE_MS);
  }

  if (!buttonDown && buttonWasDown) {
    unsigned long pressLength = millis() - buttonDownAt;
    buttonWasDown = false;

    if (pressLength >= LONG_PRESS_MS) {
      clickCount = 0;

      Serial.println("LONG PRESS detected.");
      shutdownPiAndCutPower();
    } else {
      clickCount++;
      lastClickAt = millis();
    }

    delay(DEBOUNCE_MS);
  }

  if (clickCount > 0 &&
      millis() - lastClickAt > CLICK_WINDOW_MS) {

    if (clickCount == 1) {
      Serial.println("SINGLE CLICK detected.");
      Serial.println("Sending record-toggle pulse to Pi...");
      signalPi(RECORD_PULSE_MS);
    }
    else if (clickCount == 2) {
      Serial.println("DOUBLE CLICK detected.");
      // Intentionally unused.
    }
    else if (clickCount >= 3) {
      Serial.println("TRIPLE CLICK detected.");
      tapK();
    }

    clickCount = 0;
  }
}
