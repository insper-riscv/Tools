# `pin_assignments`

Writes the pin and I/O standard assignments of the `.qsf`, deriving the others from the role.

## 1. Purpose

It is the only place that writes `set_location_assignment` and the per-instance pin assignments. The location and I/O standard come from `pins.yaml`. The other assignments are derived from the port role and are never copied from a `.qsf`.

## 2. Derived assignments

| Role | Assignments |
| :--- | :--- |
| `sdram` | `FAST_OUTPUT_REGISTER` on outputs and bidirectionals; `FAST_OUTPUT_ENABLE_REGISTER`, `FAST_INPUT_REGISTER` and `PAD_TO_INPUT_REGISTER_DELAY 0` on bidirectionals; none on the pin clock |
| `leds`, `display` | `CURRENT_STRENGTH_NEW DEFAULT` and `SLEW_RATE 1`; a family with `slew_rate: false` (MAX 10, whose fitter refuses the option on 3.3-V LVTTL pins) gets only the first |

## 3. Refusals

| Condition | Message |
| :--- | :--- |
| `inferred` pin without `--accept-inferred-pins` (V16) | `E pin M16 for SPI_FLASH_CS is inferred, not confirmed; pass --accept-inferred-pins` |
| Two signals on the same pin | `E pin X is assigned to both A and B` |

Only the signals of the ports in use enter the check, so the pin aliases of `conflicts` in `pins.yaml` that the top does not use are never assigned.

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_pin_assignments.py` | Locations and standards, I/O registers and LED assignments derived from the role, family without slew rate, V16 and repeated pin |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
