# `vhdl_style`

Checks that the VHDL files of a repository follow the style guide of the project, the one in the VHDL sections of the `CONTRIBUTING.md` of the `Core`. The repositories repeat that guide, and each one learns that a file breaks it only when somebody reviews it by hand. This module reads the files and lists each deviation with its file, line and rule, so the style is checked in the CI and not in the review.

## Rules

| Rule | What it checks |
| :--- | :--- |
| `header` | The file opens with the header block: a line of `=` (of any width), the description and a closing line |
| `libraries` | From the IEEE library, only `std_logic_1164` and `numeric_std` |
| `component` | No declaration or instantiation with `component`; the instance is direct, `u_x : entity work.x` |
| `port-map` | Every association of a `port map` is by name (`i_port => signal`) |
| `ports` | Every port starts with `i_` (input), `o_` (output and `buffer`) or `io_` (`inout`) |
| `docstrings` | Every `generic`, `port`, `constant`, `subtype`, `type`, `signal`, `alias` and `variable` has a comment on the line right above it; a comment at the end of the line or a separator-only line does not count |
| `naming` | Constants in `UPPER_SNAKE_CASE`, types and subtypes in `snake_case` with the suffix `_t`, instance labels with the prefix `u_` |

Comments and text or character literals do not count as code, so a keyword inside them raises nothing. The parameters of a function or a procedure are not declarations for the `docstrings` rule.

## What is left out

The walk is the one of `tree_check` (no hidden folders, build output or submodules) and it also leaves out what nobody edits by hand.

| File | How it is recognised |
| :--- | :--- |
| Third-party code | The `vendor/` folder |
| Quartus-generated IP | A `cyclone-v/` folder (case-insensitive), or the use of the `altera_mf` library or the text `megafunction wizard` in the file |
| Others | The globs of `tree.vhdl_style.exclude` in the `paths.yaml` of the repository, relative to the root |

```yaml
tree:
  vhdl_style:
    exclude: ["src/generated/*.vhd"]
```

## Usage

```bash
uv run riscv-tools --root <repository> check-vhdl-style
uv run riscv-tools --root <repository> check-vhdl-style --only header,ports
uv run riscv-tools --root <repository> check-tree --kind memory --only vhdl-style
```

It needs no `--config`. Each deviation prints as `STYLE <file>:<line>: <rule> <message>`, and the status is 1 with at least one deviation and 2 on an unknown rule. The `vhdl-style` rule of `check-tree` runs the same check and only runs when `--only` names it.

## CI step

Each VHDL repository calls the subcommand in a step of the `vhdl-syntax` job (or of `python-static-analysis`), after the environment is set up, once the `ci-vhdl` image carries the version of Tools that has it.

```yaml
      - name: VHDL style
        run: riscv-tools --root . check-vhdl-style
```

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_vhdl_style.py::test_a_conforming_file_has_no_violation` | A file that follows the guide passes every rule. |
| `tests/test_vhdl_style.py::test_header_is_required` | Without a header the deviation is reported on line 1. |
| `tests/test_vhdl_style.py::test_header_needs_description_and_closing_line` | A header without description or without closing line fails. |
| `tests/test_vhdl_style.py::test_header_has_no_minimum_width` | A header of 40 columns passes, and so do the ones of 80. |
| `tests/test_vhdl_style.py::test_libraries_allow_only_the_two_packages` | Another IEEE package fails. |
| `tests/test_vhdl_style.py::test_component_is_forbidden_but_not_in_comments` | `component` fails, and the comment that names it does not. |
| `tests/test_vhdl_style.py::test_port_map_must_associate_by_name` | A positional association in a `port map` fails. |
| `tests/test_vhdl_style.py::test_ports_need_the_prefix_of_their_mode` | Each mode requires its prefix. |
| `tests/test_vhdl_style.py::test_docstrings_are_needed_above_each_declaration` | A missing comment above, a comment at the end of the line and a separator fail. |
| `tests/test_vhdl_style.py::test_docstrings_cover_generics_and_skip_subprogram_parameters` | Generics need a comment and function parameters do not. |
| `tests/test_vhdl_style.py::test_naming_of_constants_types_and_labels` | Constant, type and label follow the convention. |
| `tests/test_vhdl_style.py::test_vendor_code_and_quartus_ips_are_left_out` | `vendor/` and Quartus IPs are not checked. |
| `tests/test_vhdl_style.py::test_paths_yaml_can_leave_out_more_files` | The globs of `paths.yaml` are left out. |
| `tests/test_vhdl_style.py::test_literals_and_comments_do_not_count_as_code` | A keyword in text, a character or a comment is ignored. |
| `tests/test_vhdl_style.py::test_an_unknown_rule_is_an_error` | A rule that does not exist raises. |
| `tests/test_vhdl_style.py::test_cmd_check_vhdl_style_exit_status` | The command prints OK, or exits 1 listing, or 2. |
| `tests/test_vhdl_style.py::test_the_subcommand_is_registered_without_a_config` | The subcommand runs without `--config`. |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
