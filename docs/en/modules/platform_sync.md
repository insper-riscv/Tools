# `platform_sync`

Writes the `config.yaml` of a platform for the project that consumes it. A platform keeps the paths of its `config.yaml` from the root of the repository that owns it, but the project that runs tests on it (Tests, Certification) has that repository as a submodule, and the same paths start one folder deeper. Writing the prefix by hand in each config makes the path of one file change in dozens of places when the platform is reorganized. This module resolves the `extends:` chain of the platform, puts the folder of the submodule in front of each path it owns and writes one complete file, which the variant config of the consumer extends.

## Keys that get the prefix

| Key | Content |
| :--- | :--- |
| `toolchain.specs` | The GCC specs file of the platform |
| `paths.boot_rom`, `paths.boot_rom_linker_script` | Source and linker script of the BOOT_ROM |
| `paths.sources`, `emulator.sources` | C and assembly sources of the runtime and of the Spike substitute |
| `freq_sweep.pll_file` | PLL source that the frequency sweep rewrites |
| `quartus.project_dir` | The Quartus project folder |
| `sim.vhdl_sources`, `sim.python_path` | VHDL sources of the simulation top and the testbench folder |

The consumer's paths (`paths.include_dir`, `paths.build_dir`, `paths.c_dir` and `paths.asm_dir`) and the names (`quartus.project_name`) stay as they are. So does an absolute path.

## Usage

```bash
uv run riscv-tools --root <consumer> platform sync \
  --source Insper-RISC-V/src/cyclone-v/de0-cv/config.yaml \
  --prefix Insper-RISC-V \
  --output tools/riscv_build/config.de0-cv.yaml
```

The written file starts with a header saying it is generated and where it came from. A variant config of the consumer then says `extends: config.de0-cv.yaml` and adds only its own paths.

With `--check` nothing is written, and the command exits with status 1 when the file is missing or differs from what would be written. It is the CI step that stops anyone from editing the file by hand or forgetting to regenerate it after the platform changes.

It does not need `--config`.

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_platform_sync.py::test_flatten_resolves_the_extends_chain` | The `extends:` chain of the platform is resolved |
| `tests/test_platform_sync.py::test_rebase_prefixes_every_path_the_platform_owns` | Strings and lists of paths get the prefix |
| `tests/test_platform_sync.py::test_rebase_leaves_the_consumers_paths_and_other_keys` | The consumer's paths and the names stay as they are |
| `tests/test_platform_sync.py::test_rebase_keeps_an_absolute_path_and_does_not_mutate` | An absolute path stays and the input does not change |
| `tests/test_platform_sync.py::test_sync_then_check_passes_and_a_change_fails` | The written file passes `--check` until the platform changes |
| `tests/test_platform_sync.py::test_command_runs_through_the_cli_without_config` | The command runs without `--config` |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
