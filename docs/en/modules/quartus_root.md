# `quartus_root`

Finds the Quartus installed on the machine and puts its tools on the `PATH` of `riscv-tools`.

## 1. Purpose

The Quartus Prime Lite has one folder per version, `/opt/altera_lite/<version>/quartus/bin`. On start, `riscv-tools` adds that folder to the `PATH` of its own process, so `quartus_sh`, `quartus_pgm`, `quartus_stp` and `jtagconfig` are reachable by the subprocesses without the user editing the `PATH`.

## 2. Environment variables

| Variable | Effect | Default |
| :--- | :--- | :--- |
| `QUARTUS_ROOT` | Folder that holds the Quartus versions | `/opt/altera_lite` |
| `QUARTUS_VERSION` | Version inside that folder | `25.1std` |

An empty variable counts as unset.

## 3. Order on the `PATH`

| Situation | Where the folder goes |
| :--- | :--- |
| `QUARTUS_ROOT` set by the user | At the front, and it wins over a Quartus the `PATH` already has |
| `QUARTUS_ROOT` unset | At the end, and it only serves when no other Quartus provides the tools |

The folder is added only if it exists and the `PATH` does not list it yet.

## 4. Use by the `rt` script

The `rt` script of a project reads the same two variables, mounts `QUARTUS_ROOT` read-only in the container and passes both to the `riscv-tools` inside it. The `project` module describes the script.

## 5. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_quartus_root.py` | Default folder, variables, empty variable, order on the `PATH`, missing folder and repetition |
| `tests/test_project.py` | The `rt` uses `QUARTUS_ROOT` and `QUARTUS_VERSION` |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
