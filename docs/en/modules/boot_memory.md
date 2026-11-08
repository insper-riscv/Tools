# `boot_memory`

Builds the fixed, shared bootloader (a project's own `boot_memory.S`/`boot_memory.ld`) into a flat binary and converts it to `.hex`. Built once per invocation, not once per test: BOOT_MEMORY has no test source, no `crt0` pairing, and isn't part of any test's own manifest. Every consumer that needs its image ([`sim_runner`](sim_runner.md) for GHDL, [`rom_writer`](rom_writer.md)/[`orchestrator`](orchestrator.md) for real hardware) calls `build_boot_memory` once and reuses the result, the same way a test's own compiled image gets reused across a manifest's test loop rather than rebuilt per test.

## 1. Configuration

Uses the same `toolchain.gcc`/`toolchain.objcopy` settings as [`compiler`](compiler.md), plus a project's own `paths.boot_memory`/`paths.boot_memory_linker_script` (project-specific, no default).

## 2. Prerequisites

- The RISC-V GCC toolchain (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) on `PATH`, provided by the `ci-elf` image of [insper-riscv/Infra](https://github.com/insper-riscv/Infra), or installed as in its `manual/GCC_SETUP.md`.

## 3. Tests

No automated test in this repository. A consuming project's real-hardware and simulation suites build its boot memory (`riscv-tools program`, `riscv-tools sim`), and its `sim` workflow runs it on every push.

## 4. Usage

Not its own CLI subcommand: called once at the start of a real-hardware run (before the initial `quartus_sh`/`quartus_pgm`, see [`quartus_program`](quartus_program.md)) or a simulation run (see [`sim_runner`](sim_runner.md)), never per test.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
