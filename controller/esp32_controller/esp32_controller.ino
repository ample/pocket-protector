#include <Arduino.h>
#include <Adafruit_NeoPixel.h>

// ESP32-C3 Super Mini -> Raspberry Pi recorder controller
//
// Button: ChromaTek 19mm momentary with a built-in WS2812 RGB LED.
//
// Wiring:
//   GPIO 4  -> button NO (green)          button C (white) -> common GND
//   GPIO 6  -> 330R -> button DIN (red)
//   GPIO 5  -> 1K resistor -> base of 2N2222 controlling PowerBoost K
//   GPIO 3  -> Raspberry Pi physical pin 10 (GPIO15), open-drain
//   GPIO 7  <- Raspberry Pi physical pin 13 (GPIO27), HIGH = recording
//   GPIO 10 <- Raspberry Pi physical pin 11 (GPIO17), HIGH = ready
//   Button VDD (black) -> battery +      button GND (yellow) -> common GND
//   ESP32 GND -> common ground
//
// Behavior:
//   Hold 3 s while off   -> one K tap = turn PowerBoost/Pi on
//   Hold 3 s while on    -> tell Pi to shut down, wait, then DOUBLE-TAP K
//                           to turn the PowerBoost 5V output off
//   Single click (ready) -> short LOW pulse to Pi = RECORD_TOGGLE
//
// LED:
//   Off            -> off
//   Booting        -> pulsing amber (until the Pi raises READY)
//   Ready          -> green
//   Recording      -> red
//   Shutting down  -> pulsing amber (until the 5V output is cut)
//
// GPIO3 is open-drain so the always-on ESP32 does NOT drive voltage
// into the Raspberry Pi while the Pi is powered off. The two status
// inputs use pull-downs, so they read LOW while the Pi is off.

const int BUTTON_PIN = 4;
const int K_PIN = 5;
const int PI_SIGNAL_PIN = 3;
const int LED_PIN = 6;
const int PI_RECORDING_PIN = 7;
const int PI_READY_PIN = 10;

const unsigned long DEBOUNCE_MS = 40;
const unsigned long HOLD_MS = 3000;

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

// READY must stay LOW this long before a ready Pi counts as lost,
// so a recorder service restart doesn't flicker the LED.
const unsigned long READY_LOST_MS = 2000;

// LED colors. The WS2812 is very bright behind a small lens, so these
// stay well below full scale.
const uint8_t LED_BRIGHTNESS = 80;
const uint32_t COLOR_OFF = 0x000000;
const uint32_t COLOR_READY = 0x00FF00;
const uint32_t COLOR_RECORDING = 0xFF0000;
const uint32_t COLOR_BUSY = 0xFF6000;  // amber
const unsigned long PULSE_PERIOD_MS = 1600;

enum State { OFF, BOOTING, READY, SHUTTING_DOWN };

Adafruit_NeoPixel pixel(1, LED_PIN, NEO_GRB + NEO_KHZ800);

State state = OFF;
unsigned long stateAt = 0;

bool buttonWasDown = false;
unsigned long buttonDownAt = 0;
bool holdFired = false;

unsigned long piPulseEndAt = 0;
bool piPulseActive = false;

unsigned long readyLowSince = 0;

uint32_t shownColor = 0xFFFFFFFF;


const char *stateName(State s) {
  switch (s) {
    case OFF: return "OFF";
    case BOOTING: return "BOOTING";
    case READY: return "READY";
    case SHUTTING_DOWN: return "SHUTTING_DOWN";
  }
  return "?";
}


void setState(State next) {
  Serial.printf("State: %s -> %s\n", stateName(state), stateName(next));
  state = next;
  stateAt = millis();
}


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


void startPiPulse(unsigned long pulseLengthMs) {
  // Open-drain line: LOW actively pulls the Pi input to ground.
  // updatePiPulse() releases it so the Pi's own pull-up holds it high.
  digitalWrite(PI_SIGNAL_PIN, LOW);
  piPulseEndAt = millis() + pulseLengthMs;
  piPulseActive = true;
}


void updatePiPulse() {
  if (piPulseActive && (long)(millis() - piPulseEndAt) >= 0) {
    digitalWrite(PI_SIGNAL_PIN, HIGH);
    piPulseActive = false;
  }
}


void onHold() {
  switch (state) {
    case OFF:
      Serial.println("HOLD: powering on.");
      tapK();
      setState(BOOTING);
      break;

    case BOOTING:
    case READY:
      // From BOOTING the Pi may not be listening yet; the delay before
      // cutting power still gives it the best chance to settle.
      Serial.println("HOLD: sending shutdown request to Pi...");
      startPiPulse(SHUTDOWN_PULSE_MS);
      setState(SHUTTING_DOWN);
      break;

    case SHUTTING_DOWN:
      break;
  }
}


void onClick() {
  // Don't gate on READY: if the Pi's READY line never arrives (old
  // recorder.py, loose wire) clicks would be dropped forever. A pulse
  // into a Pi that isn't listening yet is harmless.
  if (state == SHUTTING_DOWN) {
    Serial.println("Click ignored while shutting down.");
    return;
  }

  Serial.println("CLICK: sending record-toggle pulse to Pi...");
  startPiPulse(RECORD_PULSE_MS);
}


void updateButton() {
  bool buttonDown = (digitalRead(BUTTON_PIN) == LOW);
  unsigned long now = millis();

  if (buttonDown && !buttonWasDown) {
    buttonDownAt = now;
    buttonWasDown = true;
    holdFired = false;
    delay(DEBOUNCE_MS);
    return;
  }

  // Fire the hold while the button is still down, so the LED turns
  // amber at 3 s instead of waiting for release.
  if (buttonDown && !holdFired && now - buttonDownAt >= HOLD_MS) {
    holdFired = true;
    onHold();
  }

  if (!buttonDown && buttonWasDown) {
    buttonWasDown = false;

    if (!holdFired) {
      onClick();
    }

    delay(DEBOUNCE_MS);
  }
}


void updateState() {
  bool piReady = (digitalRead(PI_READY_PIN) == HIGH);
  bool piRecording = (digitalRead(PI_RECORDING_PIN) == HIGH);
  unsigned long now = millis();

  switch (state) {
    case BOOTING:
      // RECORDING going high also proves the Pi is up.
      if (piReady || piRecording) {
        setState(READY);
      }
      break;

    case READY:
      // The Pi stopped reporting ready without being asked to shut down
      // (service restart, shutdown over SSH). Show busy until it's back.
      if (piReady || piRecording) {
        readyLowSince = 0;
      } else if (readyLowSince == 0) {
        readyLowSince = now;
      } else if (now - readyLowSince >= READY_LOST_MS) {
        readyLowSince = 0;
        setState(BOOTING);
      }
      break;

    case SHUTTING_DOWN:
      if (now - stateAt >= SHUTDOWN_PULSE_MS + SHUTDOWN_CUT_DELAY_MS) {
        // FM5324HJ1: double press on K disables boost output.
        doubleTapK();
        setState(OFF);
      }
      break;

    case OFF:
      break;
  }
}


uint32_t scaleColor(uint32_t color, uint8_t level) {
  uint8_t r = ((color >> 16) & 0xFF) * level / 255;
  uint8_t g = ((color >> 8) & 0xFF) * level / 255;
  uint8_t b = (color & 0xFF) * level / 255;
  return pixel.Color(r, g, b);
}


void updateLed() {
  uint32_t color;

  switch (state) {
    case BOOTING:
    case SHUTTING_DOWN: {
      // Smooth breathe between ~10% and full brightness.
      float phase = (float)(millis() % PULSE_PERIOD_MS) / PULSE_PERIOD_MS;
      float wave = 0.5f - 0.5f * cosf(phase * 2.0f * PI);
      color = scaleColor(COLOR_BUSY, 25 + (uint8_t)(wave * 230));
      break;
    }

    case READY:
      color = digitalRead(PI_RECORDING_PIN) == HIGH
        ? COLOR_RECORDING
        : COLOR_READY;
      break;

    default:
      color = COLOR_OFF;
      break;
  }

  if (color != shownColor) {
    pixel.setPixelColor(0, color);
    pixel.show();
    shownColor = color;
  }
}


void ledSelfTest() {
  // Red, green, blue at boot. If none show, the LED's power, ground or
  // DIN wiring is wrong; if colours are swapped, change NEO_GRB.
  const uint32_t colors[] = { 0xFF0000, 0x00FF00, 0x0000FF };
  for (uint32_t c : colors) {
    pixel.setPixelColor(0, c);
    pixel.show();
    delay(300);
  }
  pixel.clear();
  pixel.show();
}


void setup() {
  Serial.begin(115200);

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(PI_RECORDING_PIN, INPUT_PULLDOWN);
  pinMode(PI_READY_PIN, INPUT_PULLDOWN);

  pinMode(K_PIN, OUTPUT);
  setKPressed(false);

  pinMode(PI_SIGNAL_PIN, OUTPUT_OPEN_DRAIN);
  digitalWrite(PI_SIGNAL_PIN, HIGH);  // release line

  pixel.begin();
  pixel.setBrightness(LED_BRIGHTNESS);
  pixel.clear();
  pixel.show();

  Serial.println("LED self-test: red, green, blue...");
  ledSelfTest();

  // If the ESP32 resets while the Pi is up, pick up where it left off.
  state = digitalRead(PI_READY_PIN) == HIGH ? READY : OFF;
  stateAt = millis();

  Serial.println();
  Serial.println("ESP32 recorder controller started.");
  Serial.println("Hold 3 s     = power on / shut down");
  Serial.println("Single click = record toggle");
  Serial.printf("Initial state: %s\n", stateName(state));
  Serial.printf("Pi READY=%d RECORDING=%d\n",
                digitalRead(PI_READY_PIN), digitalRead(PI_RECORDING_PIN));
}


void loop() {
  updateButton();
  updatePiPulse();
  updateState();
  updateLed();
  delay(10);
}
