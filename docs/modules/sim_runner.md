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

## Prerequisites

- GHDL on `PATH`.
- The `sim` extra (`uv sync --extra sim`): `cocotb` and `cocotb-tools`.

## Tests

The tests skip when GHDL or cocotb is missing.

| Test | What it verifies |
| :--- | :--- |
| `tests/test_sim_runner.py::test_sim_runner_reports_pass` | A DUT whose test passes is reported as a pass. |
| `tests/test_sim_runner.py::test_sim_runner_reports_fail` | A DUT whose test fails is reported as a fail. |
| `tests/test_sim_runner.py::test_sim_runner_parameters_reach_ghdl` | `sim.parameters` become VHDL generics at the GHDL run step. |


## Usage

```bash
uv sync --extra sim
uv run riscv-tools --config /path/to/project/config.yaml compile --emit hex
uv run riscv-tools --config /path/to/project/config.yaml sim
```

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
