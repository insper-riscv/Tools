# `bin_to_image`

Converts an already-compiled flat `.bin` into hardware/simulation-loadable formats.

## What it produces

| Format | Function | Used by |
| :--- | :--- | :--- |
| `.mif` (Intel/Altera Memory Initialization File) | `bin_to_mif` | Real hardware: baked into a Quartus project as a ROM/RAM instance's `init_file`, or JTAG-written by [`rom_writer`](rom_writer.md). |
| `.hex` (plain text, one 32-bit word per line) | `bin_to_hex` | Simulation: loaded by [`sim_runner`](sim_runner.md)'s VHDL testbench, and by [`golden_generator`](golden_generator.md)'s Spike run. |

Both pad the binary to a fixed word depth (project-specific memory size) with zero words, so a program shorter than the target memory still produces a full-depth image.

## Configuration

None: takes the binary path, output path, and word depth as direct arguments from its caller; no `config.yaml` section of its own.

## Usage

Not its own CLI subcommand: called internally by `compile --emit mif` and `compile --emit hex` (see the top-level [README](../README.md#usage)) right after [`compiler`](compiler.md) produces the `.bin`.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../LICENSE).
