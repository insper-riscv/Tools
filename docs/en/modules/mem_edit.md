# `mem_edit`

Generic In-System Memory Content Editor primitives, shared by [`rom_writer`](rom_writer.md), [`ram_zero`](ram_zero.md), [`ram_dump`](ram_dump.md), and [`htif`](htif.md). Pure mechanism, no policy: each of those modules decides which instance, address, or content to use; this module only knows how to read/write a memory instance over JTAG.

## Functions

| Function | Does |
| :--- | :--- |
| `write_full` | Overwrite a memory instance's entire depth from a `.mif`. |
| `write_full_multi` | Same, but writes the same `.mif` to several instances in one call (a design with more than one physical copy of the same content, kept in sync). |
| `write_word` | Overwrite a single word at a given offset. |
| `read_words` | Read back a range of words. |
| `dump` | Save an instance's entire content to a `.mif`. |
| `instances` | List the instances of the programmed board (index, depth, width and name), asking the board once per cable and keeping the list. |
| `invalidate` | Forget the kept lists; it runs whenever the board is programmed again, because the indices may change. |
| `rom_instances` | Return the ROM indices: it converts `quartus.rom_mem_names` or, without names, uses `quartus.rom_mem_instances`. |
| `ram_instance` | Return the RAM index: it converts `quartus.ram_mem_name` or, without a name, uses `quartus.ram_mem_instance`. |

## Resolution by name

The index of an instance changes when the design gains or loses a memory with `ENABLE_RUNTIME_MOD`, while the IP's `INSTANCE_NAME` stays; so `config.yaml` names the memories and the host finds the indices on the board.

| Situation | Result |
| :--- | :--- |
| Name and index in the same `config.yaml` | The name wins. |
| Indices only | They work as before, without asking the board. |
| Name missing on the board | Error that lists the names and indices found. |
| RAM name that fits more than one instance | Error, because the RAM cannot be told apart. |

The editor keeps only the first four characters of an `INSTANCE_NAME`: `FLASH` is listed as `FLAS`. A name listed with four characters fits every wanted name that starts with it, so `FLASH` and `FLASH_MEM` point to the instances listed as `FLAS`, and the ROM writes the same image to all of them. For the RAM, the name must differ from the others within the first four characters.

## Configuration

It takes a `JtagLink` (see [`jtag`](jtag.md)), an instance index, and paths/addresses as direct arguments; `rom_instances` and `ram_instance` read the keys `quartus.rom_mem_names`, `quartus.ram_mem_name`, `quartus.rom_mem_instances` and `quartus.ram_mem_instance`. Callers decide which instance index and depth apply to their own use case.

## Prerequisites

- Quartus Prime Lite on `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), installed as in Infra's `QUARTUS_INSTALL.md`, and a board with a USB-Blaster attached over JTAG, with the In-System Memory Content Editor instances the project's design exposes.

## Tests

No automated test in this repository. A self-hosted runner set up as in Infra's `RUNNER_SETUP.md` runs the real-hardware suite of a consuming project (`riscv-tools run`), which is the only place this module is exercised.

## Usage

Not its own CLI subcommand: it's the mechanism [`rom_writer`](rom_writer.md), [`ram_zero`](ram_zero.md), [`ram_dump`](ram_dump.md), and [`htif`](htif.md) each call to actually talk to a memory instance over JTAG.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
