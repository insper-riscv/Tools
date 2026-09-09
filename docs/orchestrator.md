# `orchestrator`

Composes every other real-hardware module into a full test-suite run, or into a clock-frequency sweep to find Fmax. The real-hardware counterpart to [`sim_runner`](sim_runner.md), which drives the same kind of run against cocotb/GHDL simulation instead of a physical board.

## Running a suite

For each test in a manifest: reload its ROM image over JTAG (see [`rom_writer`](rom_writer.md)), pulse the restart flag (see [`mailbox`](mailbox.md)), wait for the PASS/FAIL mailbox, and for `memory`-kind tests, dump and validate RAM (see [`ram_dump`](ram_dump.md), [`mem_validator`](mem_validator.md)).

If a test's mailbox never responds, three recovery tiers run in order, each only attempted if the one before it didn't already succeed:

1. **JTAG reload retry**: try the same ROM reload once more, in case the previous attempt was a one-off glitch.
2. **Reprogram from the existing `.sof`**: cheap (~10s), safe only if the VHDL source hasn't changed since that `.sof` was built (see [`quartus_program`](quartus_program.md)'s `program_only`).
3. **Full recompile + reprogram**: the slow path, only attempted if tier 2 failed specifically because the `.sof` doesn't exist yet, not because the board was simply unreachable. A full recompile produces the same bitstream tier 2 already tried, so retrying it when the board itself is the problem wastes minutes without recovering anything.

## When no automated retry can help

A failure whose own error text matches a known hardware/cable signature (e.g. `"can't scan jtag chain"`, `"jtag chain broken"`, `"hardware is not found"`) raises `NeedsHumanInterventionError` immediately, skipping the remaining tiers: none of them can fix a JTAG chain that's physically down, and grinding through recompiles at ~4-5 minutes each has been observed to recover nothing in this situation.

By default, this stops the suite and returns, saving progress so a plain re-run afterward resumes from the failed step instead of repeating completed tests. Passing `wait_for_hardware=True` instead makes it print the same message and poll `jtag.jtag_chain_healthy` (see [`jtag`](jtag.md)) every few seconds until the chain recovers on its own, e.g. after someone physically power-cycles the board, then automatically resume without a separate re-invocation. Meant for an interactive session someone is actively watching; CI keeps the default stop-and-exit behavior, since nothing there could power-cycle a board on its own anyway.

## Frequency sweep

Finds the fastest clock frequency (Fmax) a design still passes its test suite at, by rewriting the PLL (see [`freq_sweep`](freq_sweep.md)) and doing a full recompile+reprogram+compare at each candidate frequency. Full walkthrough: [docs/finding-fmax.md](finding-fmax.md).

## Configuration

| Key | Meaning |
| :--- | :--- |
| `quartus.program_wait_seconds` | How long to wait after a full reconfigure (fallback path only) before reading the mailbox (default `15`). |
| `quartus.default_timeout_s` | Default per-test timeout if a test doesn't set its own `RV32_TIMEOUT_S` header (default `15`; see [`compiler`](compiler.md)). |

## Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml run
uv run riscv-tools --config /path/to/project/config.yaml run --wait-for-hardware
uv run riscv-tools --config /path/to/project/config.yaml run --only test-a,test-b
uv run riscv-tools --config /path/to/project/config.yaml freq-sweep \
    build/real/full.mif --golden golden/full.json --start 1 --stop 30 --step 2
```

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../LICENSE).
