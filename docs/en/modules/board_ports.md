# `board_ports`

Builds the ports of a board top (name, width, direction and pin of each bit) from the roles.

## 1. Purpose

Turns the reference clock, the reset, the I/O roles, the console on pins and the device memories into ports. The pin, `.sdc` and top generators read the same ports, so the name, width and pin of each signal are born once.

## 2. Rules

| Rule | Effect |
| :--- | :--- |
| Bus formats | `LEDR[3]` and `LEDR3` form the vector `LEDR`; a stem with a single member without brackets stays scalar |
| Display | One 7-bit `HEX<d>` port per digit, from `HEX[5:0][6:0]` |
| Memory | Signals with the group prefix and `_` (`DRAM_`) form one port per stem; `signals` may be a list of prefixes |
| Missing required role | Error V5 |
| Missing optional role | Warning V6 and no port |
| Console `pinos` without a UART | Error V4 |
| Reset on a bit of another role (`KEY[0]`) | Becomes an alias (`KEY(0)`) of that role's port, with no pin of its own, so the pin is never assigned twice; without the role it becomes the scalar port `KEY_0` |

## 3. Clock that leaves by a pin

`memory_clock_port` finds the scalar output port whose name ends in `CLK` inside a memory group, the clock the `.sdc` constrains.

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_ports.py` | DE0-CV ports, flat names, reset alias, two-prefix groups, SRAM, V4 to V6 and the clock plan |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
