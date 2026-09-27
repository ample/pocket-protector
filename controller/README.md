# Controller (ESP32-C3)

An always-on ESP32-C3 Super Mini reads one momentary button with a built-in RGB LED. It tells the Pi to start or stop recording and to shut down, switches the PowerBoost's 5V output on and off, and drives the button's LED to show what the recorder is doing.

## Gestures

| Gesture | Action |
|---|---|
| Hold 3 s while off | Tap the PowerBoost K pin: power the Pi on |
| Hold 3 s while on | 1200 ms pulse to the Pi (shutdown), wait 15 s, double-tap K to cut 5V |
| Single click | 150 ms LOW pulse to the Pi: toggle recording |

Holds fire at 3 s while the button is still down, so the LED turns amber before you let go. Clicks are ignored only while shutting down. They aren't gated on READY, so recording still works if the READY line is missing. A pulse sent before the Pi is listening does nothing. The Pi distinguishes record and shutdown requests by pulse length.

## LED

| State | LED |
|---|---|
| Off | Off |
| Booting (K tapped, waiting for the Pi's READY line) | Pulsing amber |
| Ready | Green |
| Recording (Pi's RECORDING line high) | Red |

On reset the LED flashes red, green, blue. If it stays dark, check the LED's VDD, GND and DIN wiring. If the colours come out in the wrong order, change `NEO_GRB` in the sketch.
| Shutting down (until 5V is cut) | Pulsing amber |

If READY drops for more than 2 s while the Pi is up (a service restart, or a shutdown over SSH), the LED goes back to pulsing amber until READY returns.

## Button

A ChromaTek 19 mm momentary push button with a WS2812 LED. Its harness has seven wires. **Black is VDD and yellow is GND**, the reverse of the usual colours, so check these two before you power it.

| Wire | Function | Connects to |
|---|---|---|
| White | C (switch common) | GND |
| Green | NO (normally open) | ESP32 GPIO 4 |
| Blue | NC (normally closed) | Unused, insulate |
| Black | LED VDD (3.7–5 V) | Battery + |
| Red | LED DIN | ESP32 GPIO 6 via 330 Ω |
| Orange | LED DOUT | Unused, insulate |
| Yellow | LED GND | GND |

Power the LED from the raw battery, not from a 3.3 V rail or the PowerBoost output. It needs at least 3.7 V, and the PowerBoost output is off whenever the Pi is. The WS2812 draws about 1 mA even when dark.

## Wiring

| ESP32 pin | Connects to |
|---|---|
| GPIO 4 | Button NO → GND (internal pull-up) |
| GPIO 6 | 330 Ω → button LED DIN |
| GPIO 5 | 1 kΩ → base of a 2N2222 that pulls the PowerBoost K pin to ground |
| GPIO 3 | Raspberry Pi physical pin 10 (GPIO15), open-drain |
| GPIO 7 | Raspberry Pi physical pin 13 (GPIO27): RECORDING, internal pull-down |
| GPIO 10 | Raspberry Pi physical pin 11 (GPIO17): READY, internal pull-down |
| GND | Common ground |

GPIO 3 is open-drain so the ESP32 never drives voltage into a powered-off Pi. The Pi's pull-up holds the line high. The two status inputs are driven by the Pi and read LOW through the pull-downs while it's off.

## Flashing

1. Open `esp32_controller/esp32_controller.ino` in the Arduino IDE. The folder name must match the sketch name.
2. Board: **ESP32C3 Dev Module** (esp32 core by Espressif). Enable *USB CDC On Boot* to get serial output.
3. Install the **Adafruit NeoPixel** library (Library Manager).
4. Upload, then open Serial Monitor at 115200 baud to see gesture and state logs.

## Timing constants

All timings and colours are `const`s at the top of the sketch: debounce, hold threshold, K tap/gap, pulse lengths, shutdown delay, LED brightness, colours and pulse period. The K timings match the FM5324HJ1 boost IC. There, one short press is a tap and a double press turns the output off.
