# Controller (ESP32-C3)

An always-on ESP32-C3 Super Mini reads one momentary button. It tells the Pi to start or stop recording and to shut down, and it switches the PowerBoost's 5V output on and off.

## Gestures

| Gesture | Action |
|---|---|
| Single click | 150 ms LOW pulse to the Pi: toggle recording |
| Double click | Unused |
| Triple click | Tap the PowerBoost K pin: power the Pi on |
| Long press (≥2.5 s, fires on release) | 1200 ms pulse to the Pi (shutdown), wait 15 s, double-tap K to cut 5V |

The Pi distinguishes record and shutdown requests by pulse length.

## Wiring

| ESP32 pin | Connects to |
|---|---|
| GPIO 4 | Momentary button → GND (internal pull-up) |
| GPIO 5 | 1 kΩ → base of a 2N2222 that pulls the PowerBoost K pin to ground |
| GPIO 3 | Raspberry Pi physical pin 10 (GPIO15), open-drain |
| GND | Common ground |

GPIO 3 is open-drain so the ESP32 never drives voltage into a powered-off Pi. The Pi's pull-up holds the line high.

## Flashing

1. Open `esp32_controller/esp32_controller.ino` in the Arduino IDE. The folder name must match the sketch name.
2. Board: **ESP32C3 Dev Module** (esp32 core by Espressif). Enable *USB CDC On Boot* to get serial output.
3. Upload, then open Serial Monitor at 115200 baud to see gesture logs.

## Timing constants

All timings are `const`s at the top of the sketch: debounce, click window, long-press threshold, K tap/gap, pulse lengths, and the shutdown delay. The K timings match the FM5324HJ1 boost IC. There, one short press is a tap and a double press turns the output off.
