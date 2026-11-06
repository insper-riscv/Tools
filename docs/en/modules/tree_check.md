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

| `entity-coverage` | Every RTL entity of `src/` has an entry in `tests/python/tests.json` with it (or the testbench `<name>_tb`) as `toplevel` and its file in `sources`; every entity of the `formal` table has its proof in `formal/` | VHDL |
| `manifest` | The `provides` section of `paths.yaml` lists each `.vhd` of `src/` exactly once, only files that exist, and acyclic requirements; without the section the rule checks nothing | VHDL |
| `provides-required` | `paths.yaml` declares the `provides` section; a VHDL repository that loses it (through a merge or a rewrite of the file) fails instead of silently turning off the `manifest` rule and `riscv-tools sources`. The `tree.require_provides` key changes the default of the kind | all (requires it on the VHDL kinds) |

The `vhdl-style` rule is optional and only runs when `--only` names it, because the CI has a step of its own for style.

| Rule | What it checks | Kinds |
| :--- | :--- | :--- |
| `vhdl-style` | The VHDL files follow the style guide, as `check-vhdl-style` checks it (see [vhdl_style](vhdl_style.md)) | VHDL |

The `purity` rule is optional too and only runs when `--only` names it, because each repository turns it on once its vendor names are inside the vendor folders.

| Rule | What it checks | Kinds |
| :--- | :--- | :--- |
| `purity` | No board, FPGA family, device or vendor primitive name in a file outside the vendor folders (see [Purity](#purity)) | VHDL |

The coverage rule leaves out simulation models (folders `sim` and `tests`), `vendor/` code and Quartus IPs. The proof of an entity is `formal/<name>.sv`, `formal/<name>_props.sv` or `formal/<name>/props.sv`, or the files the `formal` table names for it. An exception excuses only the entity test, never the proof.

The kinds are `common-components`, `core`, `memory`, `peripherals`, `top`, `tests`, `certification`, `infra` and `tools`. The first five are the VHDL ones. Only `common-components` has no `formal/`.

The walk leaves out hidden folders, build output (`build`, `sim_build`, `output_files`, `db`, `incremental_db`), third-party code in `vendor/` and any folder that is a repository of its own, such as a submodule, whose layout is checked in its own repository. A submodule is recognized by the path declared in the root `.gitmodules`, so a copy without `.git` (made by `rsync`, for instance) also leaves it out, and by a `.git` entry inside the folder. Every rule that lists files uses this same walk: the `.vhd` files of `src/common` belong to the manifest of Common-Components and do not enter the `manifest`, `entity-coverage`, `vhdl-location`, `folder-names` and `vhdl-style` rules of the repository that mounts it.

## Configuration

No `config.yaml` section. The `paths.yaml` of the repository may have a `tree` section with the folders that are identifiers of the ISA or of a peripheral and so keep their capitals.

```yaml
tree:
  identifier_folders: [I, M, Zicsr, Zicntr, Zihpm, Zifencei, Zicclsm, ISA]
```

The coverage rule reads the `coverage` subsection. The `formal` table is a list of entities or a map from the entity to the files of its proof. The exceptions (for example a wrapper that only instantiates an IP) always carry their justification, and an exception without text or for an entity that does not exist is a problem.

```yaml
tree:
  coverage:
    formal:
      sdram_arbiter: []
      axi_master_bridge: [formal/axi_master/props.sv]
    exceptions:
      boot_memory_shell: only instantiates the IP, covered by synthesis and the board
```

The `manifest` rule reads the `provides` section at the root of `paths.yaml`. Each component lists in `sources` its files in the order GHDL analyzes them and in `requires` the components it needs: a name without a prefix belongs to the same repository, and `<repository>/<component>` to another one. The repository name comes from the `repository` key at the root, or from the folder when it is absent.

```yaml
repository: Core
provides:
  Zicntr:
    requires: [constants]
    sources: [src/Zicntr/counter64.vhd, src/Zicntr/tick_divider.vhd]
```

The `provides-required` rule demands the section on the five VHDL kinds. A repository that must not have it writes `require_provides: false` in the `tree` section, and a kind that is not VHDL asks for the section with `require_provides: true`. Any other value is a problem.

```yaml
tree:
  require_provides: true
```

## Purity

The portable part of a repository (the SoC, the core, the memories) talks to its neighbours through interface contracts and does not name a board, a family or a vendor primitive. Those names live in the vendor folders (`altera/`) and in the board data (`boards/`). In the same walk as the other rules, the `purity` rule reads the files outside those folders and reports each term it finds, with the first line and the count:

```text
TREE purity src/ROM/Cyclone-V/flash.vhd:2: primitives:altsyncram* (4x) outside the vendor folders
```

The terms are data. The file `src/riscv_tools/tree_check/purity.yaml` carries the defaults in five groups: `primitives` (`altsyncram`, `altpll`, `altera_*`, `sld_virtual_jtag`, `intended_device_family`), `families`, `boards`, `devices` and `idcodes`. The comparison ignores case, has a word boundary on the left, accepts a hyphen, an underscore, a space or nothing where the term has `-` or a space, and refuses a letter right after the term unless it ends in `*`. The same file names the vendor folders (`altera`, `boards`, at any depth, case-insensitive) and the extensions read (`.vhd`, `.vhdl`, `.v`, `.sv`, `.vh`).

The `paths.yaml` of the repository adds to this data in the `purity` subsection of the `tree` section: `terms` (group and terms), `vendor_folders`, `suffixes` and `exceptions`. An exception is a path, a folder or a pattern (`fnmatch`) with its justification. An exception without justification and one that excuses no file are problems.

```yaml
tree:
  purity:
    terms:
      boards: [new-board]
    vendor_folders: [intel]
    exceptions:
      src/legacy/top.vhd: wrapper kept until the board package exists
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
| `tests/test_submodule_exclusion.py::test_manifest_ignores_files_of_a_submodule` | The `manifest` rule does not ask for the files of a mounted submodule. |
| `tests/test_submodule_exclusion.py::test_manifest_ignores_a_submodule_without_git` | A copy without `.git` also leaves out the submodule of `.gitmodules`. |
| `tests/test_submodule_exclusion.py::test_coverage_and_location_ignore_a_submodule` | `entity-coverage` and `vhdl-location` skip the files of the submodule. |
| `tests/test_submodule_exclusion.py::test_a_folder_that_is_not_a_submodule_is_still_checked` | Only the paths of `.gitmodules` are left out. |
| `tests/test_tree_check.py::test_folder_names_reject_space_accent_and_capitals` | Space, accent and capitals in a folder name are reported. |
| `tests/test_tree_check.py::test_folder_names_accept_the_identifiers_listed_in_paths_yaml` | The identifiers listed in `paths.yaml` keep their capitals. |
| `tests/test_tree_check.py::test_folder_names_leave_out_vendor_code` | Third-party code keeps the names it came with. |
| `tests/test_tree_check.py::test_rules_depend_on_the_kind` | The VHDL rules do not apply to the other kinds. |
| `tests/test_tree_check.py::test_an_unknown_kind_or_rule_is_an_error` | A kind or rule that does not exist or apply fails. |
| `tests/test_tree_check.py::test_cmd_check_tree_exit_status` | The command prints OK, or exits 1 listing the problems, or 2 on an unknown rule. |
| `tests/test_tree_check.py::test_the_subcommand_is_registered_without_a_config` | The subcommand runs without `--config`. |
| `tests/test_entity_coverage.py::test_coverage_runs_by_default_and_style_is_opt_in` | `entity-coverage` and `manifest` run by default on the VHDL kinds, and `vhdl-style` only with `--only`. |
| `tests/test_entity_coverage.py::test_an_entity_with_its_test_passes` | A test with the entity as `toplevel` and its file in `sources` covers it. |
| `tests/test_entity_coverage.py::test_a_testbench_named_after_the_entity_covers_it` | The `toplevel` `<name>_tb` counts as the entity. |
| `tests/test_entity_coverage.py::test_an_entity_without_a_test_is_reported` | A system test that only lists the file does not cover the entity. |
| `tests/test_entity_coverage.py::test_a_test_must_list_the_file_of_the_entity` | A `toplevel` without the file in `sources` fails. |
| `tests/test_entity_coverage.py::test_models_ips_and_vendor_are_not_rtl` | Simulation models, IPs and `vendor/` need no test. |
| `tests/test_entity_coverage.py::test_an_exception_needs_a_justification` | An exception needs its justification and a stale one fails. |
| `tests/test_entity_coverage.py::test_a_named_proof_needs_its_file` | Each entity of the `formal` table needs the file of its proof. |
| `tests/test_entity_coverage.py::test_a_proof_may_follow_the_other_names_or_be_named` | `<name>_props.sv`, `<name>/props.sv` and a file named in the table count as the proof. |
| `tests/test_entity_coverage.py::test_an_exception_excuses_the_test_but_not_the_proof` | An exception excuses the entity test and keeps the proof required. |
| `tests/test_manifest_sources.py::test_without_provides_the_rule_is_silent` | Without the `provides` section, the `manifest` rule checks nothing. |
| `tests/test_manifest_sources.py::test_a_complete_manifest_passes` | Each file listed once and existing passes. |
| `tests/test_manifest_sources.py::test_unlisted_missing_duplicate_and_unknown` | A missing file, a file listed twice, a file with no component, an unknown requirement and a cycle are reported. |
| `tests/test_manifest_sources.py::test_a_malformed_manifest_is_reported` | A component without `sources` is reported. |
| `tests/test_provides_required.py::test_a_vhdl_repository_without_provides_fails` | A VHDL repository without the `provides` section fails. |
| `tests/test_provides_required.py::test_a_missing_paths_yaml_fails_too` | Without `paths.yaml` there is no section either. |
| `tests/test_provides_required.py::test_a_repository_with_provides_passes` | Declaring the section meets the rule on every kind. |
| `tests/test_provides_required.py::test_a_malformed_section_is_left_to_the_manifest_rule` | A malformed section is a problem for the `manifest` rule, not an absence. |
| `tests/test_provides_required.py::test_the_tree_section_can_opt_out` | `require_provides: false` waives the section on a VHDL kind. |
| `tests/test_provides_required.py::test_the_tree_section_can_ask_for_other_kinds` | `require_provides: true` requires the section on a non-VHDL kind. |
| `tests/test_provides_required.py::test_a_value_that_is_not_a_boolean_is_reported` | Only `true` or `false` is accepted. |
| `tests/test_provides_required.py::test_the_default_run_includes_the_rule` | A `check-tree` without `--only` already catches the loss. |
| `tests/test_entity_coverage.py::test_vhdl_style_runs_through_check_tree` | Naming `vhdl-style` in `--only` reports the deviations of the guide. |
| `tests/test_tree_purity.py::test_a_portable_tree_passes` | A file that names no board, family or primitive passes. |
| `tests/test_tree_purity.py::test_a_vendor_primitive_outside_a_vendor_folder_fails` | Each primitive of the data is reported with file and line. |
| `tests/test_tree_purity.py::test_a_board_name_fails_in_any_spelling` | Case, hyphen, underscore and a missing separator are the same board. |
| `tests/test_tree_purity.py::test_a_family_a_device_and_an_idcode_fail` | Family, device and JTAG IDCODE are board names too. |
| `tests/test_tree_purity.py::test_a_vendor_folder_is_exempt_at_any_depth` | `altera/` and `boards/` may name vendor, family and board at any depth. |
| `tests/test_tree_purity.py::test_a_word_that_only_looks_like_a_term_passes` | The word boundary lets `alteração` and `altera o valor` through. |
| `tests/test_tree_purity.py::test_only_the_listed_suffixes_are_read` | Documents and board files are not RTL sources. |
| `tests/test_tree_purity.py::test_the_first_line_and_the_count_are_reported` | Many hits of one term in a file make a single problem. |
| `tests/test_tree_purity.py::test_an_exception_excuses_a_file_a_folder_or_a_pattern` | A path, a folder and a pattern cover the files they match. |
| `tests/test_tree_purity.py::test_an_exception_needs_a_justification_and_a_file` | An exception without justification or without a file to excuse is a problem. |
| `tests/test_tree_purity.py::test_the_repository_adds_terms_folders_and_suffixes` | `paths.yaml` adds to the data without replacing it. |
| `tests/test_tree_purity.py::test_the_terms_come_from_the_data_file` | Changing `purity.yaml` changes the verdict: nothing is in the code. |
| `tests/test_tree_purity.py::test_a_submodule_is_left_to_its_own_repository` | The folders of `.gitmodules` are left out. |
| `tests/test_tree_purity.py::test_the_rule_is_opt_in_and_for_the_vhdl_kinds` | The default run leaves it out and the kinds without VHDL reject it. |
| `tests/test_tree_purity.py::test_cmd_check_tree_runs_the_rule` | The command exits 1 with a `TREE purity` line, or 0 when clean. |

## Usage

```bash
uv run riscv-tools --root <repository> check-tree --kind core
uv run riscv-tools --root <repository> check-tree --kind core --only standard-files,language-pairs
uv run riscv-tools --root <repository> check-tree --kind core --only purity
```

No `--config` needed. Status 1 and one `TREE` line per problem; made for the CI of each repository, before and after every move of files.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
