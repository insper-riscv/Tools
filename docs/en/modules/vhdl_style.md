# `vhdl_style`

Makes the [VSG](https://vhdl-style-guide.readthedocs.io) check the style of the VHDL files of a repository, with the configuration and the local rules of the project. The style guide is the one in the VHDL sections of the `CONTRIBUTING.md` of the `Core`, repeated in the repositories, and each one used to learn that a file breaks it only when somebody reviewed it by hand. The VSG is the only style tool: it brings the rules of format, naming and length, and the local rules add what the VSG does not know.

## 1. What the module keeps

| Data | Content |
| :--- | :--- |
| `vsg.yaml` | VSG configuration for the whole project, each deviation from the default justified in a comment |
| `vsg-board.yaml` | Layer for the board top-levels in `cyclone-v/`, which turns the naming rules off |
| `local_rules/` | The six local rules, one file for each, plus the `capstone_rule.py` they share |
| `vendor_primitives.yaml` | List of the vendor primitives that `component_900` accepts as `component`, each with its library and justification |

## 2. Local rules

Each rule has the identifier `<group>_900` and its message in Portuguese, with the section of `CONTRIBUTING.md` it enforces. None of them fixes the file.

| Rule | What it checks |
| :--- | :--- |
| `header_900` | The file opens with the header: a line of `=` (of any width), the description and a closing line |
| `library_900` | From the IEEE library, only `std_logic_1164` and `numeric_std` |
| `component_900` | No declaration or instance with `component`, except the vendor primitives of `vendor_primitives.yaml`; the instance is direct, `u_x : entity work.x` |
| `port_map_900` | Every association of a `port map` is by name (`i_port => signal`) |
| `process_900` | The label of every process (and the one of `end process`) starts with `p_`; a process with no label is reported by the `process_016` of the VSG |
| `docstring_900` | Every `generic`, `port`, `constant`, `subtype`, `type`, `signal`, `alias` and `variable` has a comment on the line right above; a comment at the end of the line or a separator-only line does not count |

`component_900` has no exception for our own code or for generated IP (PLLs), whose file the repository leaves out in `tree.vhdl_style.exclude` of `paths.yaml`. The only exception is the vendor primitives of `vendor_primitives.yaml`, today `altsyncram` and `sld_virtual_jtag`: the Quartus Lite exposes them only as a `component` of the `altera_mf_components` package, with no primary entity unit, and `quartus_map` 25.1 rejects `entity altera_mf.altsyncram` with error 10481. The exception holds only in a file where the library of the primitive is visible, through `library altera_mf;` or `use altera_mf.altera_mf_components.all;`. It covers the declaration, `u_x : component name` and `u_x : name`; any other name is still reported. To add a primitive, add its name, library and justification to `vendor_primitives.yaml`. The `instantiation_034` of the VSG, which does not know the list, is disabled in `vsg.yaml`. The parameters of a function or a procedure are not declarations for `docstring_900`. A VSG `--fix` that splits `signal a, b : t;` into two lines leaves the second one without a comment, and `docstring_900` reports it.

The port prefixes, the `UPPER_SNAKE_CASE` constants, the `_t` types and the `u_` instance labels and the `gen_` generate labels are rules of the VSG itself (`port_600` to `port_602`, `constant_004`, `type_600`, `subtype_600`, `instantiation_601` and `generate_017`), configured in `vsg.yaml`; all of them apply the configured prefix. The `process_600` of the VSG accepts only a suffix (`_proc`) and ignores the `prefixes` option, so it is disabled and the `p_` prefix is checked by `process_900`.

## 3. Files checked

`riscv-tools vhdl-files` lists `src/**/*.vhd` and `tests/vhdl/*.vhd`, without third-party code, submodules and what `paths.yaml` excludes.

| File | How it is recognized |
| :--- | :--- |
| Third-party code | `vendor/` folder |
| Submodule | Path in `.gitmodules` or folder with `.git`, such as `src/common` |
| Others | The globs of `tree.vhdl_style.exclude` in `paths.yaml`, relative to the root |

```yaml
tree:
  vhdl_style:
    exclude: ["src/generated/*.vhd"]
```

The board top-levels in `cyclone-v/` (in any case) are in the list but apart: `vhdl-files --board` lists them, and the VSG checks them with `vsg-board.yaml` over `vsg.yaml`. The pin and signal names come from the Quartus `.qsf` and do not follow the naming rules, but header, libraries, `component`, `port map` and docstrings apply as in the other files.

## 4. Subcommands

None needs `--config`.

| Subcommand | What it does |
| :--- | :--- |
| `vsg-config` | Prints the path of `vsg.yaml`; with `--board`, the one of `vsg-board.yaml` |
| `vsg-rules` | Prints the path of the folder with the local rules |
| `vhdl-files` | Lists the files checked, one per line; with `--board`, the board top-levels |
| `check-vhdl-style` | Shortcut that runs the VSG with the configuration and the rules of the project over those files |

`check-vhdl-style` applies the rules that the CI demands today, the five local ones plus the port prefixes, the constants, the types and the instance labels. With `--full` it applies every rule of `vsg.yaml`, including indentation, alignment, case and length. It exits with status 1 when the VSG reports a deviation.

## 5. Usage

```bash
uv run riscv-tools --root <repository> check-vhdl-style
uv run riscv-tools --root <repository> check-vhdl-style --full
uv run riscv-tools --root <repository> check-tree --kind memory --only vhdl-style
```

The VSG also runs directly, and `--fix` corrects the format:

```bash
cd <repository>
vsg -c "$(riscv-tools vsg-config)" -lr "$(riscv-tools vsg-rules)" -ap -f $(riscv-tools vhdl-files)
vsg -c "$(riscv-tools vsg-config)" "$(riscv-tools vsg-config --board)" -lr "$(riscv-tools vsg-rules)" -ap -f $(riscv-tools vhdl-files --board)
```

To deviate locally, create a `vsg.local.yaml` at the root and pass it after `vsg.yaml`, in `-c`. The `vhdl-style` rule of `check-tree` runs the same check and only enters when `--only` names it.

## 6. CI step

Each VHDL repository calls the subcommand in a step of the `vhdl-syntax` job, after setting up the environment, when the `ci-vhdl` image carries the version of Tools that has it.

```yaml
      - name: VHDL style
        run: riscv-tools --root . check-vhdl-style
```

## 7. Writing a local rule

1. A file `<group>_900.py` in `local_rules/`, with a class `rule_<group>_900` that inherits from `LocalRule` and implements `find`, returning `(line, message)` pairs.
2. The message, in Portuguese, cites the section of `CONTRIBUTING.md` it enforces.
3. The file imports only `capstone_rule`, never `riscv_tools`, because the VSG may run in an environment of its own.
4. The rule enters `GATE_RULES` in `runner.py` when the CI starts to demand it, and gets passing and failing fixtures in `tests/test_vhdl_style.py`.

## 8. Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_vhdl_style.py::test_a_conforming_file_has_no_violation` | A file that follows the guide passes every rule. |
| `tests/test_vhdl_style.py::test_header_is_required` | Without the header, the deviation is on line 1. |
| `tests/test_vhdl_style.py::test_header_needs_description_and_closing_line` | A header without description or without a closing line fails. |
| `tests/test_vhdl_style.py::test_header_has_no_minimum_width` | Headers of 40 and 100 columns pass. |
| `tests/test_vhdl_style.py::test_libraries_allow_only_the_two_packages` | Another IEEE package fails. |
| `tests/test_vhdl_style.py::test_component_is_forbidden_but_not_in_comments` | `component` fails, and a comment that names it does not. |
| `tests/test_vhdl_style.py::test_component_has_no_exception_for_generated_wrappers` | A PLL wrapper fails as well. |
| `tests/test_vhdl_style.py::test_vendor_primitive_component_is_accepted` | `altsyncram` and `sld_virtual_jtag` as `component` pass with `library altera_mf`. |
| `tests/test_vhdl_style.py::test_vendor_primitive_instance_without_keyword_is_accepted` | `u_x : altsyncram` passes with `use altera_mf...` visible. |
| `tests/test_vhdl_style.py::test_vendor_primitive_component_declaration_is_accepted` | The declaration of a listed primitive passes. |
| `tests/test_vhdl_style.py::test_vendor_primitive_needs_the_library` | Without `altera_mf` visible the primitive is reported. |
| `tests/test_vhdl_style.py::test_component_outside_the_list_is_reported` | `meu_bloco` and `pll_0002` fail even with the library. |
| `tests/test_vhdl_style.py::test_process_label_with_the_prefix_passes` | `p_x` and `p_x_proc` pass. |
| `tests/test_vhdl_style.py::test_process_label_without_the_prefix_fails` | `x` and `proc_p` fail, on the label and on `end process`. |
| `tests/test_vhdl_style.py::test_process_without_a_label_fails` | A process with no label is reported by `process_016`. |
| `tests/test_vhdl_style.py::test_the_other_prefix_rules_apply_their_prefix` | Ports, instances and generates apply the configured prefix. |
| `tests/test_vhdl_style.py::test_aligned_others_arrow_is_not_reported` | The arrow aligned after `others` is not reported (`element_association_100` disabled). |
| `tests/test_vhdl_style.py::test_component_instance_is_forbidden` | The instance `u_x : component x` fails. |
| `tests/test_vhdl_style.py::test_port_map_must_associate_by_name` | A positional association in a `port map` fails. |
| `tests/test_vhdl_style.py::test_docstrings_are_needed_above_each_declaration` | A missing comment, a trailing comment and a separator fail. |
| `tests/test_vhdl_style.py::test_docstrings_cover_generics_and_ports` | Generics and ports need a comment. |
| `tests/test_vhdl_style.py::test_docstrings_skip_subprogram_parameters` | Function parameters are not declarations. |
| `tests/test_vhdl_style.py::test_real_memory_signals_before_the_fix_pass` | The real signals of the Memory, with one comment for five names, pass. |
| `tests/test_vhdl_style.py::test_real_memory_signals_after_the_fix_fail` | The four names that `--fix` split lose their comment and fail. |
| `tests/test_vhdl_style.py::test_real_insper_signals_after_the_fix_fail` | The real signals of the Insper-RISC-V after `--fix` fail. |
| `tests/test_vhdl_style.py::test_ports_and_names_come_from_the_vsg_rules` | Prefix, constant, type and label follow the VSG rules. |
| `tests/test_vhdl_style.py::test_vendor_code_is_left_out` | `vendor/` is not listed. |
| `tests/test_vhdl_style.py::test_quartus_megafunction_files_are_listed` | A file with `altera_mf` is listed. |
| `tests/test_vhdl_style.py::test_instance_by_component_name_is_forbidden` | The instance `u_x : name` with no `entity` fails. |
| `tests/test_vhdl_style.py::test_paths_yaml_can_leave_out_more_files` | The globs of `paths.yaml` are left out. |
| `tests/test_vhdl_style.py::test_the_scope_is_src_and_the_tests_folder` | Only `src/**` and `tests/vhdl/*.vhd` are listed. |
| `tests/test_vhdl_style.py::test_submodules_are_left_out` | The files of a submodule are not listed. |
| `tests/test_vhdl_style.py::test_board_files_are_listed_apart` | The `cyclone-v/` top-levels come only with `--board`. |
| `tests/test_vhdl_style.py::test_board_files_follow_the_rules_but_not_the_naming` | A board top-level keeps its pin names and still needs a header. |
| `tests/test_vhdl_style.py::test_the_gate_accepts_what_only_the_full_check_rejects` | A long line passes by default and fails with `--full`. |
| `tests/test_vhdl_style.py::test_the_packaged_data_exist` | The configuration, the layer, the primitive list and the six rules are package files. |
| `tests/test_vhdl_style.py::test_local_rule_messages_are_in_portuguese` | The message cites the `CONTRIBUTING`. |
| `tests/test_vhdl_style.py::test_cmd_check_vhdl_style_exit_status` | The command prints OK, or exits with 1 listing. |
| `tests/test_vhdl_style.py::test_the_vsg_subcommands_print_paths_and_files` | The subcommands print paths and files. |
| `tests/test_vhdl_style.py::test_the_subcommands_are_registered_without_a_config` | The subcommands run without `--config`. |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
