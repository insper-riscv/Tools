# `vhdl_sort`

Sorts VHDL sources into GHDL-analyzable dependency order. GHDL's `-a` (analyze) phase needs a design unit's dependencies (entities it instantiates, packages it `use`s) analyzed before the unit itself; feeding files in the wrong order fails with `"primary unit ... not found"`. Hand-ordering a project's VHDL file list is tedious and breaks silently the moment a new dependency is added, so this derives the order from the files' own content instead, via lightweight regex parsing (no GHDL invocation, no real VHDL parser).

## Configuration

None: takes a list of file paths and returns them reordered; no `config.yaml` section of its own, and no project context needed at all.

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_vhdl_sort.py::test_topo_sort_orders_entity_dependency` | An entity is placed after the entities it instantiates. |
| `tests/test_vhdl_sort.py::test_topo_sort_orders_package_dependency` | A package is placed before the files that use it. |
| `tests/test_vhdl_sort.py::test_topo_sort_ignores_package_body` | A package body does not create a dependency. |
| `tests/test_vhdl_sort.py::test_topo_sort_is_deterministic_for_unrelated_files` | Unrelated files keep a stable order. |
| `tests/test_vhdl_sort.py::test_topo_sort_breaks_cycles_without_raising` | A dependency cycle is broken instead of raising. |
| `tests/test_vhdl_sort.py::test_topo_sort_skips_unreadable_file` | An unreadable file is skipped. |
| `tests/test_vhdl_sort.py::test_topo_sort_ignores_dependency_outside_input_set` | A dependency outside the input set is ignored. |


## Usage

```bash
uv run riscv-tools vhdl-sort src/**/*.vhd
```

No `--config` needed, pure file-content analysis. Useful wired into a `Makefile`'s own VHDL-syntax-check target, or to double-check a project's `sim.vhdl_sources` list is actually in dependency order before handing it to [`sim_runner`](sim_runner.md).

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
