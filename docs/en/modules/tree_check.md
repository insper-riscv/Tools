# `tree_check`

Checks that the tree of a repository follows the layout all of them share. The repositories of the project swap submodules, documents and configuration files, and each one fails only when somebody trips on what was left out of place: a `README` without its English half, a VHDL file in a folder the build does not read, a folder with a space in its name that Quartus splits in two. This module reads the tree and fails on the first change that strays from the layout, so a move of files is checked before anything is built.

## Rules

Each rule looks at one aspect of the tree and applies to some kinds of repository. The kind decides which rules run.

| Rule | What it checks | Kinds |
| :--- | :--- | :--- |
| `standard-files` | The files every repository of the kind has: licence, `README`, `CONTRIBUTING`, `AUTHORS`, `CITATION.cff`, `.gitignore` and `.github/workflows`; in the VHDL ones also `Makefile`, `paths.yaml`, `pyproject.toml`, `uv.lock`, `src/` and `tests/python/`; in those with proofs, `formal/run.sh` | all |
| `language-pairs` | `README`, `CONTRIBUTING` and `AUTHORS` exist in both languages, and every `.md` of `docs/pt-br/` has its mirror in `docs/en/` with the same path | all |
| `vhdl-location` | No `.vhd` outside `src/` and `tests/vhdl/` | VHDL |
| `common-submodule` | Common-Components is mounted at `src/common` | `core`, `memory`, `peripherals` |
| `folder-names` | Folder names in lowercase letters, digits, hyphen, dot and underscore, with no space or accent | VHDL |

Two rules are optional and only run when `--only` names them, so each repository adopts them when it meets them.

| Rule | What it checks | Kinds |
| :--- | :--- | :--- |
| `vhdl-style` | The VHDL files follow the style guide, as `check-vhdl-style` checks it (see [vhdl_style](vhdl_style.md)) | VHDL |
| `entity-coverage` | Every RTL entity of `src/` has an entry in `tests/python/tests.json` with it (or the testbench `<name>_tb`) as `toplevel` and its file in `sources`; every entity of the `formal` list has `formal/<name>.sv` | VHDL |

The coverage rule leaves out simulation models (folders `sim` and `tests`), `vendor/` code and Quartus IPs.

The kinds are `common-components`, `core`, `memory`, `peripherals`, `top`, `tests`, `certification`, `infra` and `tools`. The first five are the VHDL ones. Only `common-components` has no `formal/`.

The walk leaves out hidden folders, build output (`build`, `sim_build`, `output_files`, `db`, `incremental_db`), third-party code in `vendor/` and any folder that is a repository of its own, such as a submodule, whose layout is checked in its own repository.

## Configuration

No `config.yaml` section. The `paths.yaml` of the repository may have a `tree` section with the folders that are identifiers of the ISA or of a peripheral and so keep their capitals.

```yaml
tree:
  identifier_folders: [I, M, Zicsr, Zicntr, Zihpm, Zifencei, Zicclsm, ISA]
```

The coverage rule reads the `coverage` subsection. The exceptions (for example a wrapper that only instantiates an IP) always carry their justification, and an exception without text or for an entity that does not exist is a problem.

```yaml
tree:
  coverage:
    formal: [sdram_arbiter, axi_master_bridge]
    exceptions:
      boot_rom_shell: only instantiates the IP, covered by synthesis and the board
```

## Adoption in steps

A repository that has not finished its reorganization chooses with `--only` the rules it already meets, and the list grows at each step. A rule that does not apply to the kind is an error, not an empty step.

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_tree_check.py::test_a_conforming_tree_has_no_problem` | A tree that meets every rule passes. |
| `tests/test_tree_check.py::test_standard_files_reports_each_missing_file` | Each missing standard file is reported by name. |
| `tests/test_tree_check.py::test_common_components_needs_no_formal_folder` | The kind without proofs does not need `formal/run.sh`. |
| `tests/test_tree_check.py::test_language_pairs_reports_a_missing_half` | A `README` without its English half is reported. |
| `tests/test_tree_check.py::test_language_pairs_reports_a_document_without_its_mirror` | A document without its mirror in the other language is reported both ways. |
| `tests/test_tree_check.py::test_vhdl_location_reports_a_file_outside_src` | A `.vhd` outside `src/` and `tests/vhdl/` fails. |
| `tests/test_tree_check.py::test_vhdl_location_leaves_out_build_output_and_submodules` | Build output and submodule folders are not checked. |
| `tests/test_tree_check.py::test_common_submodule_requires_the_mount_at_src_common` | Common-Components must be declared at `src/common`. |
| `tests/test_tree_check.py::test_common_submodule_requires_the_right_repository` | The submodule at `src/common` must be Common-Components. |
| `tests/test_tree_check.py::test_common_submodule_is_reported_without_gitmodules` | Without `.gitmodules`, the submodule is not mounted. |
| `tests/test_tree_check.py::test_folder_names_reject_space_accent_and_capitals` | Space, accent and capitals in a folder name are reported. |
| `tests/test_tree_check.py::test_folder_names_accept_the_identifiers_listed_in_paths_yaml` | The identifiers listed in `paths.yaml` keep their capitals. |
| `tests/test_tree_check.py::test_folder_names_leave_out_vendor_code` | Third-party code keeps the names it came with. |
| `tests/test_tree_check.py::test_rules_depend_on_the_kind` | The VHDL rules do not apply to the other kinds. |
| `tests/test_tree_check.py::test_an_unknown_kind_or_rule_is_an_error` | A kind or rule that does not exist or apply fails. |
| `tests/test_tree_check.py::test_cmd_check_tree_exit_status` | The command prints OK, or exits 1 listing the problems, or 2 on an unknown rule. |
| `tests/test_tree_check.py::test_the_subcommand_is_registered_without_a_config` | The subcommand runs without `--config`. |
| `tests/test_entity_coverage.py::test_the_new_rules_are_opt_in` | `vhdl-style` and `entity-coverage` exist for the VHDL kinds and do not run without `--only`. |
| `tests/test_entity_coverage.py::test_an_entity_with_its_test_passes` | A test with the entity as `toplevel` and its file in `sources` covers it. |
| `tests/test_entity_coverage.py::test_a_testbench_named_after_the_entity_covers_it` | The `toplevel` `<name>_tb` counts as the entity. |
| `tests/test_entity_coverage.py::test_an_entity_without_a_test_is_reported` | A system test that only lists the file does not cover the entity. |
| `tests/test_entity_coverage.py::test_a_test_must_list_the_file_of_the_entity` | A `toplevel` without the file in `sources` fails. |
| `tests/test_entity_coverage.py::test_models_ips_and_vendor_are_not_rtl` | Simulation models, IPs and `vendor/` need no test. |
| `tests/test_entity_coverage.py::test_an_exception_needs_a_justification` | An exception needs its justification and a stale one fails. |
| `tests/test_entity_coverage.py::test_a_named_proof_needs_its_file` | Each entity of the `formal` list needs `formal/<name>.sv`. |
| `tests/test_entity_coverage.py::test_vhdl_style_runs_through_check_tree` | Naming `vhdl-style` in `--only` reports the deviations of the guide. |

## Usage

```bash
uv run riscv-tools --root <repository> check-tree --kind core
uv run riscv-tools --root <repository> check-tree --kind core --only standard-files,language-pairs
```

No `--config` needed. Status 1 and one `TREE` line per problem; made for the CI of each repository, before and after every move of files.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
