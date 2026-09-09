# `jtag`

Identifies the live JTAG connection and runs this package's bundled `.tcl` scripts against it. The shared plumbing every other JTAG-touching module ([`mem_edit`](mem_edit.md), [`rom_writer`](rom_writer.md), [`ram_zero`](ram_zero.md), [`ram_dump`](ram_dump.md), [`mailbox`](mailbox.md), [`quartus_program`](quartus_program.md)) builds on.

## Identifying a connection: `JtagLink`

A JTAG connection needs two identifiers, and they behave differently over time:

| Field | What it is | Stability |
| :--- | :--- | :--- |
| `hardware_name` | The `"USB-Blaster [<bus>-<port>]"` cable name | Drifts across reboots/hub renumbering, so it's always live-detected via `detect_jtag_hardware()`, never read from config. |
| `device_name` | The target chip's JTAG identity string | Stable across reboots; comes from a project's own config (`quartus.jtag_device`). |

## Chain health

`jtag_chain_healthy()` runs `jtagconfig` and returns `False` if its output contains "chain broken" (case-insensitive) or if `jtagconfig` itself fails to run at all (cable unplugged, driver issue); `True` otherwise. Meant to be polled in a loop, e.g. while waiting for someone to physically power-cycle a wedged board (see [`orchestrator`](orchestrator.md)).

## Configuration

| Key | Meaning |
| :--- | :--- |
| `quartus.jtag_device` | The FPGA's own JTAG IDCODE string. No default; every project must set this explicitly. |

## Usage

Not its own CLI subcommand: every other JTAG-touching module takes a `JtagLink` as an argument rather than constructing one itself, and calls `jtag.run`/`jtag.run_tcl` to actually invoke a `.tcl` script against it.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
