# `htif`

Reads the HTIF `tohost`, the 64-bit word a test writes its result to on completion, and writes `fromhost` to tell the parked core to restart from its entry point. Also generates `rv32_test.h`, the C header a test `#include`s to finish, from a project's own `config.yaml` (so a consuming project never hand-writes and maintains a copy that could drift out of sync with its actual `memory.tohost_addr`).

## The `tohost` convention

The low word of `tohost` is `0` while the test runs. A test that passed writes `1`. A test that failed writes `(code << 1) | 1`, with a nonzero `code`, the number of the `RV32_FAIL(code)` call that failed. The host sees the end by bit 0 set. `fromhost` sits 8 bytes above `tohost`, and a restart is any nonzero value written to it.

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
| `quartus.poll_interval_seconds` | How often to re-read `tohost` while waiting for a result (default `0.5`). |
| `memory.ram_base` | RAM's base byte address. No default; project-specific. |
| `memory.tohost_addr` | Byte address of `tohost` (8 bytes). No default; project-specific. |
| `memory.fromhost_addr` | Byte address of `fromhost` (8 bytes). No default; project-specific. |

## Prerequisites

- Quartus Prime Lite on `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), installed as in Infra's `QUARTUS_INSTALL.md`, and a board with a USB-Blaster attached over JTAG, with the In-System Memory Content Editor instances the project's design exposes.

## Tests

No automated test in this repository. A self-hosted runner set up as in Infra's `RUNNER_SETUP.md` runs the real-hardware suite of a consuming project (`riscv-tools run`), which is the only place this module is exercised.

## Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml htif read
uv run riscv-tools --config /path/to/project/config.yaml htif restart
uv run riscv-tools --config /path/to/project/config.yaml generate-header
```

`read`/`restart` are mostly for manual debugging; [`orchestrator`](orchestrator.md) calls the same functions directly as part of its own per-test loop.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
