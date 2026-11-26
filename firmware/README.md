# Rig firmware

`rigidflex_rig/` is the sketch for the pull-test rig's ESP32. It needs the Arduino IDE (or `arduino-cli`) with the **esp32** board package, core 2.x or 3.x. It uses no extra libraries.

- **Step pulses** come from a hardware PWM channel (LEDC), so the test speed is exact and steady. Position is integrated from the frequency actually generated.
- **Force** comes from the HX711, read bit by bit at up to 80 samples/s. It is calibrated with `tare` and `cal <newtons>`, and the scale is kept in flash.
- **Stop rule** (in `rig_core.h`): the pull stops on a break (force below 25 % of the peak for 3 samples, once the peak is over 5 N), at the set travel, at 470 N, on the button, on the end stop, or when any byte arrives over USB.
- **Protocol:** plain text at 115200 baud. The command list is at the top of the sketch. `rigidflex rig`, `rigidflex stiffness` and `rigidflex test` speak it for you.

The logic that decides when to stop, the position maths and the command parser live in `rig_core.h`, which has no hardware dependencies. `tests/firmware_sim.cpp` runs them on a normal computer as part of the test suite: simulated breaks, noise, overload, the micros() wrap-around and the parser. The CI also compiles the full sketch for the ESP32.

Pins and wiring: [docs/pull_rig.md](../docs/pull_rig.md#wiring).
