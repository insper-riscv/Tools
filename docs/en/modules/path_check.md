# `path_check`

Checks that every file path a project's configuration references exists. Moving a VHDL file between repositories breaks every list that names it: the simulation's source list, the tests' `tests.json`, the Quartus project's `VHDL_FILE` lines. Each breaks only when something runs it. This module reads those lists and fails when a listed path does not exist, so a move is checked before anything is built.

## Configuration

No `config.yaml` section: a manifest lists the references, passed with `--manifest`.

```yaml
references:
  - name: sim sources
    file: Tests/tools/riscv_build/config.yaml   # relative to --root
    yaml: sim.vhdl_sources                      # dotted path; `*` walks a mapping's values or a list
    base: Tests                                 # what the paths are relative to (default: the file's directory)
  - name: quartus project
    file: tests/FPGA/core/quartus/core_fpga_test.qsf
    pattern: 'VHDL_FILE (\S+)'                  # group 1 of every match
  - name: directories
    paths: [src, tests/FPGA]                    # literal, relative to --root
```

- `base` is `@file` (the referencing file's directory) by default, or a directory relative to `--root`.
- A value with an environment variable (`$QUARTUS_ROOTDIR/...`) is skipped: it depends on the machine.
- A reference that yields no path fails, so a list renamed or reformatted out of reach is noticed; `optional: true` allows it.

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_path_check.py::test_collect_reads_a_yaml_list_relative_to_base_and_skips_env_vars` | A YAML list resolves against `base`; values with `$VARIABLE` are skipped. |
| `tests/test_path_check.py::test_collect_walks_a_wildcard_over_a_mapping` | `*` walks the values of a mapping (`tests.json`'s `*.sources`). |
| `tests/test_path_check.py::test_collect_defaults_base_to_the_files_directory` | Without `base`, paths are relative to the referencing file. |
| `tests/test_path_check.py::test_check_passes_when_every_path_exists` | YAML, JSON, `.qsf` and literal references all pass when the files exist. |
| `tests/test_path_check.py::test_check_reports_a_path_that_was_moved` | A moved file is reported once per list that names it. |
| `tests/test_path_check.py::test_check_fails_when_a_reference_yields_nothing` | A renamed or reformatted list fails instead of passing empty. |
| `tests/test_path_check.py::test_check_allows_an_optional_reference_to_yield_nothing` | `optional: true` allows an empty reference. |
| `tests/test_path_check.py::test_check_reports_an_unreadable_file_and_a_bad_entry` | An absent file and a malformed entry are reported. |
| `tests/test_path_check.py::test_cmd_check_paths_exit_status` | The command prints OK, or exits 1 listing the problems. |

## Usage

```bash
uv run riscv-tools --root <project> check-paths --manifest paths.yaml
```

No `--config` needed. Exit status 1 and one `PATH` line per problem; meant for CI, before and after each file move.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
