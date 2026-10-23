# `sdram_debug`

Reads and writes words of the SDRAM through its JTAG debug port: the counterpart of [`mem_edit`](mem_edit.md) for a RAM that is outside the FPGA. The debug port is a second master of the SDRAM controller behind a Virtual JTAG instance (the protocol is in Memory's `docs/SDRAM_DEBUG.md`), so the host can read and write the memory with the core running, stopped or hung.

A word address counts 32-bit words from the base of the SDRAM. [`ram_target`](ram_target.md) chooses between this module and `mem_edit` for a project's RAM; the other modules do not call it directly.

## Functions

| Function | Does |
| :--- | :--- |
| `read_words(link, word_address, word_count)` | reads contiguous words |
| `write_word(link, word_address, value, byte_enable)` | writes one word, bytes by `byte_enable` |
| `fill(link, word_address, word_count, value)` | fills a range; the board runs it, so zeroing the 64 MB takes about two seconds and not one shift per word |

## Configuration

| Key | Meaning |
| :--- | :--- |
| `quartus.ram_backend` | `sdram_debug` makes the RAM the SDRAM behind this port; the default, `ismce`, is a memory instance of the FPGA |

## Prerequisites

- Quartus Prime Lite on `PATH` (`quartus_stp`), and a board with a USB-Blaster whose design has the debug port (the SDRAM platform of TopLevel).

## Tests

`tests/test_sdram_debug.py` runs the module against a stand-in for the script. On the board, the SDRAM platform of TopLevel runs the real-hardware suite through it.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
