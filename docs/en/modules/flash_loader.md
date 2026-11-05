# `flash_loader`

Writes and reads the one-copy internal FLASH through its JTAG loader: the equivalent of [`mem_edit`](mem_edit.md) for a dual-port FLASH, which Quartus Lite does not let the In-System Memory Content Editor rewrite. The loader is a Virtual JTAG instance in front of port B of the FLASH (the protocol is in `docs/en/rom/flash_loader.md` of Memory) and writes only while the core is halted.

A word address counts 32-bit words from the start of the FLASH IP. [`rom_writer`](rom_writer.md) chooses between this module and `mem_edit` through the `quartus.rom_write_method` key.

## Functions

| Function | Does |
| :--- | :--- |
| `load_image(link, words, word_address, restart)` | halts the core, writes the image in a few long scans, compares the count and the checksum the loader reports and, with `restart` true, releases the core, which restarts from the BOOT_ROM |
| `read_words(link, word_address, word_count)` | halts the core and reads contiguous words; the core stays halted |
| `halt(link)` | halts the core |
| `release(link)` | releases the core |
| `image_checksum(first_word, words)` | sum of each word with its address, modulo $2^{32}$, the same the loader keeps |

$$\text{sum} = \sum_{i} \left( \text{word}_i + \text{address}_i \right) \bmod 2^{32}$$

## Configuration

| Key | Meaning |
| :--- | :--- |
| `quartus.rom_write_method` | `jtag_loader` makes `rom_writer` a caller of this module; the default, `mem_edit`, uses the In-System Memory Content Editor |

## Prerequisites

- Quartus Prime Lite on `PATH` (`quartus_stp`) and a board with a USB-Blaster whose project has the FLASH loader (the `internal-mem` platform of Insper-RISC-V).

## Tests

`tests/test_flash_loader.py` runs the module against a stand-in for the script. On the board, the hardware suite of the `internal-mem` platform goes through it.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
