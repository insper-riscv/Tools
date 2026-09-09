# `mailbox`

Reads a fixed RAM word (the "mailbox") that a test writes `PASS`/`FAIL` to on completion, and pulses a "go flag" word that tells the running core to restart from its entry point. Also generates `rv32_test.h`, the C header a test `#include`s to signal PASS/FAIL, from a project's own `config.yaml` (so a consuming project never hand-writes and maintains a copy that could drift out of sync with its actual `memory.mailbox_addr`).

## Word offsets: relative vs. absolute

A byte address can be converted to a word offset two different, non-interchangeable ways whenever `ram_base != 0`:

| Mode | Formula | Used by |
| :--- | :--- | :--- |
| Relative (default) | `(addr - ram_base) // 4` | [`mem_edit`](mem_edit.md)'s JTAG primitives, since the In-System Memory Content Editor addresses RAM through its own 0-based internal word index, not the CPU's byte address. |
| Absolute | `addr // 4` | Anything reasoning about the CPU's own byte-addressed view of memory. |

## Configuration

| Key | Meaning |
| :--- | :--- |
| `quartus.ram_mem_instance` | Instance index for the RAM debug tap (default `1`). |
| `quartus.poll_interval_seconds` | How often to re-read the mailbox while waiting for a result (default `0.5`). |
| `memory.ram_base` | RAM's base byte address. No default; project-specific. |
| `memory.mailbox_addr` | Byte address of the PASS/FAIL word. No default; project-specific. |
| `memory.go_flag_addr` | Byte address of the restart flag word. No default; project-specific. |

## Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml mailbox read
uv run riscv-tools --config /path/to/project/config.yaml mailbox pulse
uv run riscv-tools --config /path/to/project/config.yaml generate-header
```

`read`/`pulse` are mostly for manual debugging; [`orchestrator`](orchestrator.md) calls the same functions directly as part of its own per-test loop.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../LICENSE).
