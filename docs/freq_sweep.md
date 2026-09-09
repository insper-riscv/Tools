# `freq_sweep`

Edits a project's PLL source file in place to change its output clock frequency (and, for a multi-phase PLL, its phase offsets). Purely a text rewrite: no hardware/JTAG interaction here, and recompiling/reprogramming after the edit is the caller's job (see [`orchestrator`](orchestrator.md)'s frequency sweep).

The parameter-name patterns, unit strings, and how many phase-shifted clock outputs to rewrite all come from a project's own `freq_sweep:` config section rather than being hardcoded, so a project with a differently named PLL megafunction instance, or a VHDL rather than Verilog wrapper (as long as it uses the same `.param("value")` instantiation syntax), configures this without touching this module's code.

## Configuration

| Key | Meaning |
| :--- | :--- |
| `freq_sweep.pll_file` | Path to the PLL source file. No default; project-specific. |
| `freq_sweep.phase_count` | How many equally phase-spaced clock outputs the PLL instance has (default `1`, a plain single-phase PLL). |
| `freq_sweep.freq_param_template` | `"{idx}"`-templated frequency parameter name (default `"output_clock_frequency{idx}"`, matching Quartus' `altpll` megafunction). |
| `freq_sweep.phase_param_template` | Same, for phase offset (default `"phase_shift{idx}"`). |
| `freq_sweep.freq_unit` | Unit suffix written after the frequency value (default `"MHz"`). |
| `freq_sweep.phase_unit` | Unit suffix written after the phase value (default `"ps"`). |

## Usage

Not its own CLI subcommand: called internally by [`orchestrator`](orchestrator.md)'s `freq-sweep` command at each candidate frequency, before a recompile+reprogram+compare. Full walkthrough: [docs/finding-fmax.md](finding-fmax.md).

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../LICENSE).
