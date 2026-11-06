# `display`

Reads and writes the seven-segment display register of the platform through the Virtual JTAG: the six digits are a 24-bit register that the program or the host writes (the `seg_display` block is in the [Peripherals](https://github.com/insper-riscv/Peripherals) repository). The module also holds the failure flag of the session, which keeps the first red LED lit, and it is how `run` and `certify-board` show the running program.

## Functions

| Function | Does |
| :--- | :--- |
| `read_display(link)` | reads the 24-bit value of the register |
| `write_display(link, value)` | writes a value of up to 24 bits and returns what the board confirms |
| `write_fail(link, failed)` | turns the failure flag (the first red LED) on or off |
| `check_display(link, count)` | writes `count` pseudo-random values and reads each back, to prove the path from the JTAG to the register |
| `encode_test(number)` | register value while program number `number` (1 to 999999) runs, with the six digits in decimal |
| `encode_act(number)` | register value while ACT4 ELF number `number` (1 to 9999) runs: `A` and `C` on HEX5 and HEX4 and the number in decimal on HEX3 to HEX0, so the first ELF shows `AC0001` |

## Command

```bash
riscv-tools --config <config.yaml> display [VALUE | --check N]
```

With no argument the command only reads the register. With `VALUE` (six hexadecimal digits, HEX5 first) it writes it, and `--check N` runs the check of `N` writes and reads and exits with status 1 if any value comes back different.

`run` shows the program number when `orchestrator.board_display` is true, and `certify-board` shows the ELF number when `act.board_display` is true. In both cases the first red LED stays lit after the first failure or timeout.

## Prerequisites

- Quartus Prime Lite on `PATH` (`quartus_stp`), and a board with a USB-Blaster whose design has the display register behind a Virtual JTAG instance (the `de0-cv` of Insper-RISC-V).

## Tests

`tests/test_display.py` covers the encoding of the numbers, the reading of the script output and the refusal of out-of-range values. `tests/test_runner_display.py` covers the use of the display by `run`.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
