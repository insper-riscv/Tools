# `ram_target`

Where a project's RAM lives, and how the host reaches it over JTAG. `mailbox`, `ram_dump` and `ram_zero` take a RAM target and call this module, so they work with either kind of RAM.

| Target | The RAM is | Reached through |
| :--- | :--- | :--- |
| an `int` | a memory instance inside the FPGA | [`mem_edit`](mem_edit.md), by the instance index |
| `SdramDebugRam` | the SDRAM | [`sdram_debug`](sdram_debug.md) |

`target_from_config(cfg)` picks one from `quartus.ram_backend` (`ismce`, the default, with `quartus.ram_mem_instance`, or `sdram_debug`).

A RAM of 64 MB cannot be dumped whole over JTAG, and a golden only checks a few words. For the SDRAM, `ram_dump` saves a sparse `.mif` with just the words the golden names (`mem_validator.golden_word_offsets`), which `mem_validator` reads like any other dump. `riscv-tools dump-ram --start-word N --words M` does the same by hand.

## Tests

`tests/test_sdram_debug.py`.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
