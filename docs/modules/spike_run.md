# `spike_run`

Runs a compiled test's ELF to completion under Spike and reports PASS or FAIL, with no hardware and no simulator involved. It is a fast software check to run before a real-hardware or simulation suite: `riscv-tools spike-run` reads the manifest `compile --emit mif` wrote and runs every test in it.

## How a verdict is read

The test's `crt0.S` writes `1` to HTIF `tohost` for a pass and `3` for a fail. Spike exits with that value shifted right by one, so:

| `tohost` | Spike exit status | Result |
| :--- | :--- | :--- |
| `1` | `0` | PASS |
| `3` | `1` | FAIL |
| never written | (killed at the timeout) | FAIL, reported as timed out |

## Configuration

| Key | Meaning |
| :--- | :--- |
| `emulator.spike_bin` | Name or path of the `spike` binary (default `spike`); see [golden_generator](golden_generator.md) for its requirements. |
| `emulator.tohost_symbol` | Symbol the test writes its verdict to (default `tohost`). |
| `emulator.entry_symbol` | Symbol execution starts at (default `_start`). |
| `emulator.timeout_s` | Seconds to wait when a test has no `RV32_TIMEOUT_S` header (default `60`). A test's own `RV32_TIMEOUT_S` takes precedence. |
| `toolchain.nm`, `toolchain.objcopy` | Resolve the entry and `tohost` symbols and add `fromhost` to a temporary ELF copy when the link script doesn't define it. |
| `memory.*` | The ROM and RAM regions handed to Spike's `-m`, the same ones [golden_generator](golden_generator.md) uses. |

A project with a separate boot ROM (`paths.golden_linker_script` and `paths.boot_rom`) is run through the same self-contained ELF the golden generator builds, since the FLASH-only image has no entry point Spike can start from.

## Prerequisites

- `spike` on `PATH`, installed as in [insper-riscv/Infra](https://github.com/insper-riscv/Infra)'s `SPIKE_SETUP.md` (the build keeps Spike's debug module away from address 0).
- the RISC-V GCC toolchain (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) on `PATH`, installed as in [insper-riscv/Infra](https://github.com/insper-riscv/Infra)'s `GCC_SETUP.md` (`nm` and `objcopy`; `gcc` builds the fixtures).

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_spike_run.py::test_run_elf_reports_pass_when_tohost_is_1` | `tohost = 1` is a pass with exit status 0. |
| `tests/test_spike_run.py::test_run_elf_reports_fail_when_tohost_is_3` | `tohost = 3` is a fail with exit status 1. |
| `tests/test_spike_run.py::test_run_elf_times_out_when_tohost_is_never_written` | A test that never writes `tohost` is reported as timed out. |
| `tests/test_cli_compile.py::test_cmd_spike_run_passes_compiled_tests` | `spike-run` reports PASS for compiled tests from a manifest. |
| `tests/test_cli_compile.py::test_cmd_spike_run_rejects_a_test_missing_from_the_manifest` | `--only` with an unknown name exits with an error. |


## Usage

```bash
uv run riscv-tools --config /path/to/project/config.yaml compile --emit mif
uv run riscv-tools --config /path/to/project/config.yaml spike-run
uv run riscv-tools --config /path/to/project/config.yaml spike-run --only add,mem
```

The exit status is `1` when any test fails, which makes it usable as a CI gate. The full output is also written to `<run_log.logs_dir>/spike/latest.log`.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
