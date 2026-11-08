# `quartus_program`

The slow "base" path: a full `quartus_sh --flow compile` followed by `quartus_pgm`, or a reprogram-only shortcut when the bitstream hasn't changed. Meant to run once up front to establish a baseline bitstream, and again as a fallback if a JTAG-reloaded test (see [`rom_writer`](rom_writer.md), [`htif`](htif.md)) times out, in case the board itself wedged rather than the test hanging.

## 1. Two entry points

| Function | Does | Cost |
| :--- | :--- | :--- |
| `full_reconfigure` | Bakes a `.mif` in as the ROM's `init_file`, compiles the whole Quartus project, then programs the board. | Minutes (full synthesis). |
| `program_only` | Reprograms from an already-built `.sof`, no recompile. | Seconds. Only safe if the VHDL source hasn't changed since that `.sof` was built. |

`full_reconfigure` always shells the compile and program steps out together as one `bash -c` chain, never as two separate Python subprocess calls: invoking `quartus_pgm` as its own subprocess immediately after `quartus_sh` has been observed to break the JTAG chain (`Error 213019: Can't scan JTAG chain`), while chaining the same two commands inside one shell process does not.

## 2. Compile options

`program` accepts, besides the `.mif`, the options below. With none of them the flow is the usual one: `quartus_sh --flow compile` followed by `quartus_pgm`. With `--seed`, `--generic` or `--stop-after`, the compile goes through the single script `tcl/compile.tcl`, which replaces the per-platform `<project>_synth.tcl`.

| Option | Effect |
| :--- | :--- |
| `--seed N` | Placement seed (script default 5); the script also fixes the `HIGH PERFORMANCE EFFORT` mode |
| `--generic NAME=VALUE` | Changes an integer top-level generic for this compile only, without writing it to the `.qsf`; repeatable |
| `--stop-after map\|fit\|sta` | Stops after synthesis, fitting or timing analysis; the board is not programmed |
| `--compile-only` | Runs the whole flow and does not program the board |
| `--board NAME` (global) | Picks the cable by the FPGA IDCODE of the board, through the board selection of `jtag_link` |
| `--project-dir`, `--project-name` | Quartus project in place of `quartus.project_dir` and `quartus.project_name`, for a project written by `board generate`; the `.sof` is `output_files/<name>.sof` |

The `.mif` is required only when the board is programmed. With `--compile-only` or `--stop-after`, no cable is consulted.

| Stop point | Stages run |
| :--- | :--- |
| `map` | Synthesis |
| `fit` | Synthesis and fitting |
| `sta` | Synthesis, fitting and timing analysis |
| full | `execute_flow -compile` |

## 3. Configuration

| Key | Meaning |
| :--- | :--- |
| `quartus.project_dir` | Path to the Quartus project directory. No default; project-specific. |
| `quartus.project_name` | Quartus project/revision name passed to `quartus_sh --flow compile`. No default. |
| `quartus.sof_file` | Path (relative to `project_dir`) to the compiled `.sof`. No default. |
| `quartus.rom_mif_target` | Path (relative to `project_dir`) the ROM megafunction reads its `init_file` from at compile time. No default. |
| `quartus.stale_cache_dirs` | Directories deleted before every compile (default `["db", "incremental_db", "output_files", "simulation"]`), since a ROM megafunction's `init_file` is a string parameter Quartus' own incremental build cache doesn't track as a project source. |

## 4. Prerequisites

- Quartus Prime Lite on `PATH` (`quartus_sh`, `quartus_pgm`), installed as in Infra's `QUARTUS_INSTALL.md`, a Quartus project, and a board attached over JTAG.

## 5. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_program_options.py` | `compile.tcl` records the same calls as `de0-cv_synth.tcl`, the compile-and-program chain, `program_only` against `de0-cv_program.sh` and `cmd_program` with the new options |

The old scripts stay as test fixtures (`tests/fixtures/multifpga/handwritten/`), run under `tclsh` with the Quartus commands replaced by recorders.

## 6. Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml program <path-to.mif>
```

Also called internally by [`orchestrator`](orchestrator.md) as the initial reconfigure step of a full suite run, and as its own automatic recovery tier when a JTAG-reloaded test's `tohost` never changes.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
