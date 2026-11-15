# `ram_dump`

Saves a RAM instance's entire content to a `.mif` over JTAG. Used for `RV32_TEST_KIND: memory` tests, where the PASS/FAIL result alone isn't enough to prove a test did the right thing (it wrote the right values to memory, not just that it reached its own pass signal): see [`mem_validator`](mem_validator.md), which compares the resulting dump against a golden JSON.

## 1. Region in the SDRAM

With `--region FLASH` or `--region RAM` the command reads a range of a region that sits in the SDRAM, in its window of the chip ([`sdram_windows`](sdram_windows.md)), instead of the RAM instance of the FPGA.

| Option | Effect |
| :--- | :--- |
| `--range ADDRESS:LENGTH` | Byte address of the SoC and length in bytes of the range, for example `0x41FFF000:0x1000` |
| `--full` | Reads the whole region, in bursts when the bitstream has them ([`sdram_debug`](sdram_debug.md), section 3) |
| `--platform` | `platform.yaml` (relative to `--root`) that gives the windows, in place of `memory.sdram_windows` |

An output file with the extension `.bin` receives the bytes, and any other extension receives a `.mif` with one line per word, numbered from the start of the region. The read is valid with the core running, because the data cache is write-through and the SDRAM holds the latest value.

## 2. Configuration

| Key | Meaning |
| :--- | :--- |
| `quartus.ram_mem_name` | Name (the IP's `INSTANCE_NAME`, e.g. `RAM`) of the RAM instance; it wins over `quartus.ram_mem_instance`. |
| `quartus.ram_mem_instance` | Instance index Quartus' In-System Memory Content Editor assigns to the RAM debug tap. `1` is the common case. |

## 3. Prerequisites

- Quartus Prime Lite on `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), installed as in Infra's `QUARTUS_INSTALL.md`, and a board with a USB-Blaster attached over JTAG, with the RAM instance the project's design exposes.

## 4. Tests

No automated test in this repository. A self-hosted runner set up as in Infra's `RUNNER_SETUP.md` runs the real-hardware suite of a consuming project (`riscv-tools run`), which is the only place this module is exercised.

## 5. Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml dump-ram <output.mif>
```

Also called internally by [`orchestrator`](orchestrator.md) after each `memory`-kind test, before handing the dump to [`mem_validator`](mem_validator.md).

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
