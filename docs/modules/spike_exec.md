# `spike_exec`

Prepares and launches Spike runs. It is the shared step behind [`golden_generator`](golden_generator.md) and [`spike_run`](spike_run.md): neither builds a Spike command line or touches an ELF on its own.

## What it does

| Step | Behaviour |
| :--- | :--- |
| Preflight | Finds `emulator.spike_bin` on `PATH` (or as a path) and probes it once per process. A Spike that places its debug module at address 0 aborts with `devices at [0, 1000) and [0, 10000) overlap` whenever the target's ROM starts at address 0, so it is rejected with a pointer to Infra's `SPIKE_SETUP.md`. |
| ELF preparation | Copies the ELF to a temporary directory and, with `objcopy --add-symbol`, defines what Spike needs: `fromhost` right after `tohost` when the link script doesn't define it (without both, Spike warns and never exits on completion), a `tohost` alias when `emulator.tohost_symbol` names it differently, and any extra symbols a caller asks for (such as `begin_signature`). The original ELF is never modified. |
| Command line | `--isa`, one `-m` region per real memory, `--disable-dtb` and `--pc`. Spike's own default memory sits at `0x80000000` and its reset vector goes through a boot ROM at `0x1000`, both of which collide with a target whose memory starts near address 0. |

## Configuration

| Key | Meaning |
| :--- | :--- |
| `emulator.spike_bin` | Name or path of the `spike` binary (default `spike`). |
| `emulator.tohost_symbol` | Symbol the program writes on completion (default `tohost`). |
| `toolchain.nm`, `toolchain.objcopy` | Resolve symbol addresses and add symbols to the ELF copy. |

## Prerequisites

- `spike` on `PATH`, installed as in [insper-riscv/Infra](https://github.com/insper-riscv/Infra)'s `SPIKE_SETUP.md` (the build keeps Spike's debug module away from address 0).
- The RISC-V GCC toolchain (`riscv32-unknown-elf-nm` and `-objcopy`) on `PATH`, installed as in Infra's `GCC_SETUP.md`.

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_spike_exec.py::test_require_spike_missing_binary_points_at_setup_doc` | A missing Spike raises an error that points at `SPIKE_SETUP.md`. |
| `tests/test_spike_exec.py::test_require_spike_rejects_debug_module_at_address_zero` | A Spike whose debug module overlaps a ROM at address 0 is rejected. |
| `tests/test_spike_exec.py::test_require_spike_accepts_a_binary_without_the_overlap` | A Spike without the overlap is accepted. |
| `tests/test_spike_exec.py::test_spike_command_lists_every_region_and_the_entry_point` | The command line carries every memory region, the entry point and the extra arguments. |
| `tests/test_spike_exec.py::test_prepared_elf_adds_fromhost_and_extra_symbols` | `fromhost` and the requested symbols are added to a temporary copy, and the original is untouched. |
| `tests/test_spike_exec.py::test_prepared_elf_aliases_a_custom_tohost_symbol` | A project's own `tohost` name gets a `tohost` alias. |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
