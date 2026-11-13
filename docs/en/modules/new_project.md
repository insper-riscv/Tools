# `new_project`

Creates a project for a known board. Inside the `dev_tools` image, one command downloads the `Insper-RISC-V` repository with its submodules, copies the platform of the board under the new name, writes the `platform.yaml` from the choices, registers the platform in the repository, generates the files that follow from it and prints a short help with tips to change the project.

## Usage

```bash
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/w/.home \
  -v "$PWD":/w -w /w ghcr.io/insper-riscv/dev_tools:latest \
  riscv-tools new-project --new "de0-cv-64k" --board de0-cv \
  --profile rv32im_zicclsm_zicntr_zihpm \
  --rom 64K --ram 64K --icache 32768 --dcache 32768
```

The project is left in `./de0-cv-64k/Insper-RISC-V`, inside the mounted folder, and stays after the container ends. A name such as `--new "Meu Projeto de Teste"` is left in `./meu-projeto-de-teste/Insper-RISC-V`. It does not need `--config`.

## Options

| Option | Effect |
| :--- | :--- |
| `--new` | Name of the project, required: letters (upper and lower case, with accents), digits, spaces, hyphens and underscores; empty, only spaces or any other character is refused |
| `--board` | Board of the catalog (`boards/`); an unknown board is refused with the list of known ones |
| `--profile` | Profile of the core; without it, the starting platform's profile stands |
| `--rom`, `--ram` | Size of the FLASH region and of the RAM, such as `64K` or `1M` |
| `--icache`, `--dcache` | Size of the cache in bits, or `off` |
| `--dir` | Folder the project is created in (default `.`) |
| `--source` | Address of the `Insper-RISC-V` repository to download |
| `--repo` | Uses an existing clone instead of downloading one |
| `--no-generate` | Writes the platform and does not generate the files that follow from it |
| `--lang` | Language of the printed help, `pt` or `en` (default `pt`) |

A memory option that is not given keeps the value of the starting platform.

## What the command does

1. Downloads the repository with its submodules, or uses the clone of `--repo`.
2. Checks the name (and derives the identifier), the board, the profile and the sizes. The profile must be among those that `Core/profiles/matrix.yaml` expands and have Zifencei when the BOOT_MEMORY of the start executes `fence.i` (without the extension the instruction is illegal and the boot restarts forever), the ROM must be a multiple of two 4 KiB sectors (two banks) and the RAM a multiple of 4 KiB.
3. Picks the starting platform: the only one outside `calibration/` that lists the board and has a `top`.
4. Works out the new `platform.yaml` and the edits of `paths.yaml` before writing anything, so a repository that does not have the expected shape does not get a half-made folder.
5. Copies the platform folder, renames files and VHDL names and gives the simulation top an entity of its own.
6. Writes the `platform.yaml` and registers the platform in `paths.yaml` (the list of platforms and the components of the map, the board top and the simulation top) and in the script of source lists.
7. Generates the memory map and the source lists, checks the map and writes the Quartus project.
8. Writes the `project.yaml`, the `README.md` and the `rt` script into the project folder, which the `project` module uses ([docs/modules/project.md](project.md)).
9. Prints the help.

## Edits to `platform.yaml`

The file of the starting platform is edited line by line, and its comments stay. A header above everything marks the file as created by the command, so a created platform is never picked as the start of another.

| Choice | Lines changed |
| :--- | :--- |
| Name | `platform` and `top` |
| `--profile` | `profile` |
| `--rom` | Size of the FLASH region and the two `flash` banks, split in whole sectors |
| `--ram` | Size of the RAM region and the `stdout`, `tohost` and `fromhost` words at its top |
| `--icache`, `--dcache` | The cache line in `memory`, with `enabled: false` for `off` |

The peripherals, clocks, inputs and outputs and interrupts come from the starting platform. A starting platform that lacks one of the expected lines is refused, naming the line.

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_new_project.py::test_sizes_are_read_in_bytes` | `64K`, `1M` and numbers become bytes |
| `tests/test_new_project.py::test_a_malformed_size_is_refused` | Malformed sizes are refused |
| `tests/test_new_project.py::test_caches_are_a_size_or_off` | A cache is a number of bits or `off` |
| `tests/test_new_project.py::test_the_choices_are_checked_against_the_catalog` | An invalid name, board, profile or size is refused |
| `tests/test_new_project.py::test_a_profile_without_zifencei_is_refused_when_the_boot_needs_it` | Without Zifencei the profile is refused when the BOOT_MEMORY executes `fence.i`, with the right profile in the message |
| `tests/test_new_project.py::test_a_boot_without_fence_i_accepts_any_profile` | Without `fence.i` in the BOOT_MEMORY the profile is free |
| `tests/test_new_project.py::test_the_host_words_sit_at_the_top_of_the_ram` | The host words follow the end of the RAM |
| `tests/test_new_project.py::test_the_flash_splits_into_two_banks_of_whole_sectors` | The banks fill whole sectors |
| `tests/test_new_project.py::test_the_platform_file_follows_the_choices` | The `platform.yaml` reflects every choice and keeps the comments |
| `tests/test_new_project.py::test_a_choice_left_out_keeps_the_template_value` | An omitted choice keeps the starting value |
| `tests/test_new_project.py::test_a_template_without_the_expected_line_is_refused` | A missing expected line is an error |
| `tests/test_new_project.py::test_names_are_renamed_in_text` | Folder, VHDL names and project names are renamed, without duplicating |
| `tests/test_new_project.py::test_the_template_is_the_platform_of_the_board` | The start is the only platform of the board |
| `tests/test_new_project.py::test_paths_gain_the_platform_and_its_three_components` | `paths.yaml` gains the platform and the three components |
| `tests/test_new_project.py::test_the_script_gains_a_line_or_reports_none` | The script gains the line, or the command warns there is none to copy |
| `tests/test_new_project.py::test_the_platform_is_created_and_registered` | Files, entity and registrations change |
| `tests/test_new_project.py::test_nothing_is_copied_when_the_repository_cannot_be_edited` | No half-made folder is left |
| `tests/test_new_project.py::test_an_existing_platform_is_not_overwritten` | An existing platform is not overwritten |
| `tests/test_new_project.py::test_the_command_prints_the_help_and_runs_without_config` | The command runs without `--config` and prints the help |
| `tests/test_new_project.py::test_the_help_can_be_printed_in_english` | `--lang en` prints the help in English |
| `tests/test_new_project.py::test_the_command_refuses_an_unknown_board` | An unknown board exits with status 1 |
| `tests/test_new_project.py::test_a_name_gives_a_slug` | Case, accents, spaces, underscores and hyphens become an identifier |
| `tests/test_new_project.py::test_a_name_with_forbidden_characters_is_refused` | Empty, only spaces, slash, dot, quotes, control, shell and YAML are refused |
| `tests/test_new_project.py::test_a_name_whose_slug_does_not_start_with_a_letter` | The identifier passes the same check as before |
| `tests/test_new_project.py::test_the_name_goes_to_the_header_manifest_help_and_readme` | The typed name shows in the header, manifest, help and README |
| `tests/test_new_project.py::test_a_dangerous_name_is_refused_before_anything_is_written` | A dangerous name exits with status 1 and creates nothing |
| `tests/test_new_project.py::test_two_names_with_one_slug_collide_and_say_the_slug` | Two names with one identifier collide and the message names it |
| `tests/test_new_project.py::test_an_existing_project_folder_is_refused_with_the_slug` | An existing identifier folder is refused |
| `tests/test_new_project.py::test_the_positional_name_is_gone` | The positional argument no longer exists |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
