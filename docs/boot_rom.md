# `boot_rom`

Builds the fixed, shared bootloader (a project's own `boot_rom.S`/`boot_rom.ld`) into a flat binary and converts it to `.hex`. Built once per invocation, not once per test: BOOT_ROM has no test source, no `crt0` pairing, and isn't part of any test's own manifest. Every consumer that needs its image ([`sim_runner`](sim_runner.md) for GHDL, [`rom_writer`](rom_writer.md)/[`orchestrator`](orchestrator.md) for real hardware) calls `build_boot_rom` once and reuses the result, the same way a test's own compiled image gets reused across a manifest's test loop rather than rebuilt per test.

## Configuration

Uses the same `toolchain.gcc`/`toolchain.objcopy` settings as [`compiler`](compiler.md), plus a project's own `paths.boot_rom`/`paths.boot_rom_linker_script` (project-specific, no default).

## Usage

Not its own CLI subcommand: called once at the start of a real-hardware run (before the initial `quartus_sh`/`quartus_pgm`, see [`quartus_program`](quartus_program.md)) or a simulation run (see [`sim_runner`](sim_runner.md)), never per test.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../LICENSE).
