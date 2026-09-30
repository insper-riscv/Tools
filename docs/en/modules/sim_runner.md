# `sim_runner`

Drives cocotb/GHDL simulation, the simulation-side counterpart to [`orchestrator`](orchestrator.md), which drives real hardware over JTAG instead. Owns no DUT-specific knowledge itself: a project's own cocotb `test_module` (see Configuration below) knows the actual VHDL signal hierarchy and polls the PASS/FAIL mailbox from simulated signals directly, the same convention [`mailbox`](mailbox.md) uses for real hardware.

Needs the optional `sim` extra (`cocotb` + `cocotb-tools`, plus GHDL on `PATH`); not a hard dependency of the package, so projects that only use the real-hardware side don't need it installed.

## Configuration

| Key | Meaning |
| :--- | :--- |
| `sim.toplevel` | Top-level VHDL entity GHDL elaborates and cocotb attaches to. No default; project-specific. |
| `sim.vhdl_sources` | VHDL source files, in dependency order (see [`vhdl_sort`](vhdl_sort.md)). No default. |
| `sim.test_module` | The project's own cocotb test module. No default; it's the piece that knows the DUT's signal names and polls its mailbox. |
| `sim.ghdl_std` | VHDL standard GHDL analyzes against (default `"08"`, VHDL-2008). |
| `sim.parameters` | VHDL generics set on the toplevel at GHDL's run step, e.g. a sim-only ROM model that loads its image via a generic rather than an env var. Empty by default. |
| `sim.image` | `hex` (default) or `mif`: the image the simulation loads, see Simulating with the hardware memories below. |
| `sim.ghdl_flags` | Extra GHDL arguments, applied at the analyze, elaborate and run steps. Empty by default. |
| `sim.libraries` | VHDL libraries analyzed once before the sources, as `{library: [files]}`. Empty by default. |
| `sim.run_files` | Files copied into each test's run directory, as `{file name: source}`. Empty by default. |
| `sim.env` | Extra environment variables for the cocotb test module, as `{name: template}`. Empty by default. |

The last four are templates: `{hex_path}`, `{mif_path}`, `{boot_rom_hex_path}` and `{boot_rom_mif_path}` are replaced per test (see [configuration.md](../configuration.md)).

## Simulating with the hardware memories

By default the simulation loads `.hex` images into plain VHDL array models of the memories. A design whose hardware top instantiates the vendor's memory IP (Quartus `altsyncram`) can be simulated with that IP instead, so the simulated memories behave as the ones on the FPGA do. The pieces, all configuration:

1. `sim.image: mif`, so each test loads the `.mif` that `compile --emit mif` writes and that the hardware loads, and so the boot ROM's `.mif` is built too.
2. `sim.libraries`, with the vendor library (for Quartus, `altera_mf_components.vhd` then `altera_mf.vhd` from the installation's `eda/sim_lib` directory, through an environment variable so the path is not fixed) and `sim.ghdl_flags` with what that library needs (`-fsynopsys -fexplicit -frelaxed`). The library is analyzed once per `sim` run, into `<build_dir>/sim/sim_work/libraries`.
3. `sim.run_files`, because the IP reads its initial content from a file name fixed in the VHDL (for instance `init.mif`): each entry copies the test's image, or the boot ROM's, to that name in the run directory.
4. `sim.env`, to tell a test module written for a different top (other clock and reset names, other timeout) what to drive.

The clock and PLL are not part of this: a PLL's simulation model is usually not VHDL (Quartus' is SystemVerilog, which GHDL does not run), so the design provides a behavioral stand-in with the same ports and parameters.

The `extends:` key of the project's config lets this be a short second config file next to the default one, and `--config` picks it.

## Prerequisites

- GHDL on `PATH`.
- The `sim` extra (`uv sync --extra sim`): `cocotb` and `cocotb-tools`.
- With `sim.libraries`: the vendor's simulation library sources.

## Tests

The tests skip when GHDL or cocotb is missing.

| Test | What it verifies |
| :--- | :--- |
| `tests/test_sim_runner.py::test_sim_runner_reports_pass` | A DUT whose test passes is reported as a pass. |
| `tests/test_sim_runner.py::test_sim_runner_reports_fail` | A DUT whose test fails is reported as a fail. |
| `tests/test_sim_runner.py::test_sim_runner_parameters_reach_ghdl` | `sim.parameters` become VHDL generics at the GHDL run step. |
| `tests/test_sim_runner.py::test_sim_runner_libraries_flags_run_files_and_env` | A separately analyzed library is found, `sim.ghdl_flags` reach it, `sim.run_files` land in the run directory and `sim.env` reaches the cocotb module. |
| `tests/test_sim_runner.py::test_sim_runner_env_reaches_the_test_module` | A wrong expected value in `sim.env` fails the test, so the previous one proves the value arrives. |
| `tests/test_sim_runner.py::test_build_libraries_needs_the_flags_the_library_needs` | A library that needs `-fsynopsys` fails to analyze without it. |
| `tests/test_sim_runner.py::test_expand_env_replaces_variables` | `$VAR` and `${VAR}` in a path are replaced from the environment. |
| `tests/test_sim_runner.py::test_expand_env_rejects_an_unset_variable` | An unset variable is an error that names it. |
| `tests/test_config_extends.py` | `extends:` merges over the base, replaces lists, is relative to the file that names it, rejects a loop, and leaves a config without it unchanged. |

## Usage

```bash
uv sync --extra sim
uv run riscv-tools --config /path/to/project/config.yaml compile --emit hex
uv run riscv-tools --config /path/to/project/config.yaml sim
```

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
