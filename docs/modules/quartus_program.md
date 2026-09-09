# `quartus_program`

The slow "base" path: a full `quartus_sh --flow compile` followed by `quartus_pgm`, or a reprogram-only shortcut when the bitstream hasn't changed. Meant to run once up front to establish a baseline bitstream, and again as a fallback if a JTAG-reloaded test (see [`rom_writer`](rom_writer.md), [`mailbox`](mailbox.md)) times out, in case the board itself wedged rather than the test hanging.

## Two entry points

| Function | Does | Cost |
| :--- | :--- | :--- |
| `full_reconfigure` | Bakes a `.mif` in as the ROM's `init_file`, compiles the whole Quartus project, then programs the board. | Minutes (full synthesis). |
| `program_only` | Reprograms from an already-built `.sof`, no recompile. | Seconds. Only safe if the VHDL source hasn't changed since that `.sof` was built. |

`full_reconfigure` always shells the compile and program steps out together as one `bash -c` chain, never as two separate Python subprocess calls: invoking `quartus_pgm` as its own subprocess immediately after `quartus_sh` has been observed to break the JTAG chain (`Error 213019: Can't scan JTAG chain`), while chaining the same two commands inside one shell process does not.

## Configuration

| Key | Meaning |
| :--- | :--- |
| `quartus.project_dir` | Path to the Quartus project directory. No default; project-specific. |
| `quartus.project_name` | Quartus project/revision name passed to `quartus_sh --flow compile`. No default. |
| `quartus.sof_file` | Path (relative to `project_dir`) to the compiled `.sof`. No default. |
| `quartus.rom_mif_target` | Path (relative to `project_dir`) the ROM megafunction reads its `init_file` from at compile time. No default. |
| `quartus.stale_cache_dirs` | Directories deleted before every compile (default `["db", "incremental_db", "output_files", "simulation"]`), since a ROM megafunction's `init_file` is a string parameter Quartus' own incremental build cache doesn't track as a project source. |

## Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml program <path-to.mif>
```

Also called internally by [`orchestrator`](orchestrator.md) as the initial reconfigure step of a full suite run, and as its own automatic recovery tier when a JTAG-reloaded test's mailbox never responds.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
