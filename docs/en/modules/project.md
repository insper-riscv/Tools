# `project`

Short commands to work on a project made by `new-project`, without typing the options of `riscv-tools` or of Quartus. The project remembers its own board and platform in a `project.yaml` file, and a script `rt` in the project folder runs `riscv-tools` in the `dev_tools` image with the computer's Quartus.

## The `rt` script

`new-project` writes `rt` into the project folder. It mounts the project folder, the computer's Quartus (read only) and the computer's network into the container, and runs `riscv-tools` there. Before that it calls the computer's `jtagconfig`, which starts the `jtagd` that the container reaches over the network; without that server the container does not see the USB-Blaster cable.

| Variable | Effect |
| :--- | :--- |
| `QUARTUS_ROOT` | Folder where Quartus is installed (default `/opt/altera_lite`) |
| `RISCV_TOOLS_HOST` | Name of the computer in the lock of the board (default `hostname -s`) |
| `RISCV_TOOLS_IMAGE` | Image to use (default `ghcr.io/insper-riscv/dev_tools:latest`) |

Any subcommand goes through the script, for example `./rt project build` or `./rt profiles --spec ...`. On a Docker daemon with user remapping, `--network host` is refused unless the run also uses `--userns=host`.

## Usage

```bash
./rt project doctor
./rt project build
./rt project flash Tests/build-de0-cv-64k/arithmetic-add.mif
./rt project help
```

| Action | What it does |
| :--- | :--- |
| `doctor` | Checks the platform files, the Quartus tools on the `PATH` and the JTAG cable; exits with status 1 when a file or a tool is missing, and only warns when there is no cable |
| `build` | Builds the Quartus project up to the `--stop-after` step (`map`, `fit` or `sta`, default `sta`), without programming the board |
| `flash FILE.mif` | Locks the board, compiles, programs the bitstream and embeds the program, on the configuration of `Tests` (`Tests/tools/riscv_build/config.<slug>.yaml`, written by step 3 of `help`); waits in line if someone else has the board |
| `help` | Prints how to run the tests and compile a program of your own, with this platform's addresses |

The command looks for the `project.yaml` in the folder of `--dir` (default `.`) and in the folders above it. It does not need `--config`.

## The `project.yaml`

| Field | Content |
| :--- | :--- |
| `name` | Name of the project, as typed |
| `slug` | Identifier derived from the name; names the folder, the platform and the files |
| `board` | Board of the catalog |
| `repo` | Folder of the `Insper-RISC-V` clone, from the project |
| `platform` | Folder of the platform, from the clone |

## The tests help

The `help` action explains, in order, how to download the `Tests` repository, point it at the project's platform, write the derived configuration and the header of the map, compile and run the existing tests and compile a C program of your own. The addresses of the map header come from the project's `platform.yaml`, worked out on the spot: the end of the RAM, the host words and the two FLASH banks.

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_project.py::test_the_manifest_is_written_and_read_back` | The four fields survive being written |
| `tests/test_project.py::test_the_manifest_is_found_from_a_folder_inside` | The search climbs from a subfolder to the project |
| `tests/test_project.py::test_a_missing_or_incomplete_manifest_is_an_error` | With no file or a missing field, the error says what to do |
| `tests/test_project.py::test_the_launcher_mounts_the_quartus_and_shares_the_network` | The script is executable, valid shell and lends the Quartus and the network |
| `tests/test_project.py::test_build_stops_after_the_chosen_quartus_step` | The command is `program --stop-after` on the platform's configuration |
| `tests/test_project.py::test_flash_holds_the_lock_of_the_board` | The program runs inside `board lock --wait` on the same board, on the Tests configuration |
| `tests/test_project.py::test_flash_needs_the_tests_to_be_prepared` | Without the Tests configuration, the error says to prepare Tests |
| `tests/test_project.py::test_the_cable_is_found_by_the_idcode_of_the_board` | The cable is found by the IDCODE of the board, even with several boards on the computer |
| `tests/test_project.py::test_the_idcode_comes_from_the_board_catalog` | The IDCODE comes from the JTAG chain of the catalog |
| `tests/test_project.py::test_the_launcher_takes_the_same_lock_as_the_host` | The `rt` shares `/tmp` and the host name, to take the same lock |
| `tests/test_project.py::test_the_files_of_the_platform_are_checked` | A missing file fails with advice |
| `tests/test_project.py::test_the_quartus_tools_are_looked_up_on_the_path` | A missing tool fails and points to `./rt` |
| `tests/test_project.py::test_a_missing_cable_is_a_warning_not_a_failure` | A missing cable only warns |
| `tests/test_project.py::test_the_header_constants_follow_the_platform` | The header values come from the map |
| `tests/test_project.py::test_the_tests_help_names_the_project_and_the_program` | The help uses the project's names in both languages |
| `tests/test_project.py::test_the_project_command_runs_build_in_the_checkout` | The `build` runs in the clone with the right configuration |
| `tests/test_project.py::test_flash_without_an_image_exits_with_status_one` | The `flash` requires the `.mif` |
| `tests/test_project.py::test_the_project_command_needs_a_project` | Outside a project, the error points to `new-project` |
| `tests/test_project.py::test_the_project_command_prints_the_tests_help` | The `help` prints the platform's values |
| `tests/test_new_project.py::test_the_command_writes_the_manifest_and_the_launcher` | `new-project` writes the `project.yaml` and the `rt` |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
