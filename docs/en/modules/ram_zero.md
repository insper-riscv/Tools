# `ram_zero`

Clears every word of a RAM instance over JTAG, without reprogramming the board. Internally just writes a full-depth all-zero `.mif` via [`mem_edit.write_full`](mem_edit.md): "zero it" is "write this specific content" rather than a dedicated zeroing primitive on the Quartus side.

## Configuration

| Key | Meaning |
| :--- | :--- |
| `quartus.ram_mem_instance` | Instance index Quartus' In-System Memory Content Editor assigns to the RAM debug tap. `1` is the common case (RAM instantiated right after ROM). |
| `memory.ram_words` | RAM depth in words, project-specific. |

## Prerequisites

- Quartus Prime Lite on `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), installed as in Infra's `QUARTUS_INSTALL.md`, and a board with a USB-Blaster attached over JTAG, with the RAM instance the project's design exposes.

## Tests

No automated test in this repository. A self-hosted runner set up as in Infra's `RUNNER_SETUP.md` runs the real-hardware suite of a consuming project (`riscv-tools run`), which is the only place this module is exercised.

## Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml zero-ram
```

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
