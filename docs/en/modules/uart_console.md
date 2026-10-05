# `uart_console`

Shows what a program prints while it runs, through the JTAG UART of the platform: a UART whose other end is a Virtual JTAG instance (the registers and the scan protocol are in Memory's `docs/EXTERNAL_BUS.md`). It is the live view next to [`sdram_debug`](sdram_debug.md), which reads the stdout buffer after the fact: the UART shows the output of a program that is still running, or stuck, and gives it input.

The console scans the UART back to back; each scan brings up to four bytes. The UART is the second Virtual JTAG instance of the design; the SDRAM debug port is the first.

## Functions

| Function | Does |
| :--- | :--- |
| `read_console(link, on_bytes, seconds, send)` | listens for `seconds` seconds (0 until interrupted), calls `on_bytes` with each chunk as it arrives, gives the program the bytes of `send` first, and returns everything read |
| `decode_line(line)` | decodes one output line of the script into bytes, or `None` for a line that carries no data |

## Command

```bash
riscv-tools --config <config.yaml> console [--seconds N] [--send TEXT]
```

A program prints to the UART only once a host has scanned it, so start the console before or while the program runs; a program that finds nobody listening does not wait for one. When the program prints faster than the console reads (about four bytes per scan), it waits for room in the queue up to a bound, then drops the byte; the stdout buffer in the SDRAM keeps every byte up to its size.

## Prerequisites

- Quartus Prime Lite on `PATH` (`quartus_stp`), and a board with a USB-Blaster whose design has the JTAG UART (the SDRAM platform of TopLevel).

## Tests

`tests/test_uart_console.py` runs the module against a stand-in for the script. In simulation, the SDRAM platform of TopLevel reads its UART the same way during every program and compares the stream with the stdout buffer.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
