# `vhdl_sort`

Sorts VHDL sources into GHDL-analyzable dependency order. GHDL's `-a` (analyze) phase needs a design unit's dependencies (entities it instantiates, packages it `use`s) analyzed before the unit itself; feeding files in the wrong order fails with `"primary unit ... not found"`. Hand-ordering a project's VHDL file list is tedious and breaks silently the moment a new dependency is added, so this derives the order from the files' own content instead, via lightweight regex parsing (no GHDL invocation, no real VHDL parser).

## Configuration

None: takes a list of file paths and returns them reordered; no `config.yaml` section of its own, and no project context needed at all.

## Usage

```bash
uv run riscv-tools vhdl-sort src/**/*.vhd
```

No `--config` needed, pure file-content analysis. Useful wired into a `Makefile`'s own VHDL-syntax-check target, or to double-check a project's `sim.vhdl_sources` list is actually in dependency order before handing it to [`sim_runner`](sim_runner.md).

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../LICENSE).
