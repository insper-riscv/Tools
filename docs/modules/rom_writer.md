# `rom_writer`

Loads a new ROM image into an already-programmed board over JTAG, without a full recompile/reprogram. Pairs with [`mailbox`](mailbox.md)'s restart "go flag" pulse to make the core jump back to its entry point and run the newly written image (see a consuming project's own `crt0.S`).

A project with more than one physical copy of the same ROM content (see [`quartus_program`](quartus_program.md)'s `rom_mif_target`/`rom_mem_instances`) writes to every listed instance in one call, keeping all copies in sync.

## Configuration

| Key | Meaning |
| :--- | :--- |
| `quartus.rom_mem_instances` | Instance index/indices Quartus' In-System Memory Content Editor assigns to the ROM debug tap(s), in declaration order in the project. `[0]` is the common case (a single ROM instantiated first). |
| `memory.rom_words` | ROM depth in words, project-specific. Used to validate/format a program's `.mif` before writing it. |

## Prerequisites

- Quartus Prime Lite on `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), installed as in Infra's `QUARTUS_INSTALL.md`, and a board with a USB-Blaster attached over JTAG, with the ROM instances the project's design exposes.

## Tests

No automated test in this repository. A self-hosted runner set up as in Infra's `RUNNER_SETUP.md` runs the real-hardware suite of a consuming project (`riscv-tools run`), which is the only place this module is exercised.


## Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml write-rom <path-to.mif>
```

Also called internally by [`orchestrator`](orchestrator.md)'s per-test JTAG-reload loop, the fast path used instead of a full recompile between tests.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
