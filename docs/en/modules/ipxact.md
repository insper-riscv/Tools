# `ipxact`

Generates and checks the IP-XACT descriptions ([IEEE Std 1685-2022](https://standards.ieee.org/ieee/1685/10199/)) of the VHDL blocks of a repository. The VHDL is the source of truth, and the XML files are generated, versioned and checked by CI, never edited by hand.

## 1. Commands

| Command | What it does |
| :--- | :--- |
| `riscv-tools --root <repository> ipxact extract` | Prints the generics and ports of every entity, read from the VHDL |
| `riscv-tools --root <repository> ipxact generate` | Writes `ipxact/<name>.<version>.component.xml` for every entity and validates what it wrote |
| `riscv-tools --root <repository> ipxact generate --check` | Writes nothing; fails when a versioned document differs from what the VHDL gives |
| `riscv-tools --root <repository> ipxact check` | Fails when a document is missing, one is left over, one differs from the VHDL or the standard rejects one |

None of them needs `--config`. `generate` and `check` exit with status 1 on any problem and with status 2 when the repository has no `provides` manifest.

## 2. Extracting the VHDL

The sources follow the order of the `provides` manifest (see [sources](sources.md)). For each component of the manifest, the module analyzes the dependency closure with `ghdl -a --std=08 -Werror` into a temporary library and exports the syntax tree with `ghdl --file-to-xml`. The entities of the component files come from that tree.

| VHDL element | IP-XACT element |
| :--- | :--- |
| `natural`, `positive`, `integer` generic | `ipxact:parameter` of type `int`, with the `minimum` and `maximum` of the subtype |
| `boolean` generic | `ipxact:parameter` of type `bit`, with value `0` or `1` |
| `std_logic` or `std_logic_vector` generic | `ipxact:parameter` of type `bit`, with a sized value (`8'hA5`) |
| `string` generic | `ipxact:parameter` of type `string` |
| `std_logic`, `std_logic_vector`, `unsigned`, `signed`, `bit`, `bit_vector` port | `ipxact:port` with `ipxact:wire`, direction and `wireTypeDef` |
| Port of a vector-array type declared in a package | `ipxact:wire` with one `ipxact:vector` per dimension |
| Vector limits and defaults | SystemVerilog expressions of the generics (`(width - 1)`) |

The comment right above each generic and port becomes the `ipxact:description`, and the first line of text of the file header becomes the component description.

### 2.1. Expressions

IP-XACT accepts only parameter identifiers in an expression (SCR 5.18), so the module writes each limit with the generics as identifiers. A package constant is replaced by its value, and a function call is handled as follows.

| Call in the VHDL | Result |
| :--- | :--- |
| `pick(c, a, b)` | `(c ? a : b)`, or the chosen value when `c` is constant |
| `log2_ceil(x)` and `log2_exact(x)` | `$clog2(x)` (clause E.5.1) |
| Function whose body is a sequence of `return` and `if` without `else` | The expanded body, with the arguments in place of the parameters |
| Any other function | Refused, with the VHDL line |

A construct with no IP-XACT form (an integer-typed port, a limit given by an attribute) produces no document unless the entity is listed in `ipxact.exceptions` of `paths.yaml`, with the justification. `check` fails when an exception covers an entity that translates or no entity at all.

### 2.2. Vendor libraries

A file that names a library other than `ieee`, `std` and `work` (such as `altera_mf`, which comes with Quartus) is analyzed with only the entity declaration: the lines that name the library become comments and everything after the end of the entity is blanked, keeping the line numbers.

## 3. The generated document

| Part | Content |
| :--- | :--- |
| VLNV | Vendor `insper.edu.br`, library of the repository (`common`, `core`, `memory`, `peripherals`, `top`), entity name and the version from the `pyproject.toml` of the repository |
| `ipxact:model` | `rtl` view (`VHDL:*:*`), `rtl_instantiation` instantiation with `moduleParameters` bound to the parameters, and the ports |
| `ipxact:fileSets` | `rtl_sources` set with the files of the manifest component, type `vhdlSource-2008` |
| `ipxact:parameters` | One `user` parameter per generic, with the default from the VHDL |
| `ipxact:vendorExtensions` | The manifest component and its `requires` (project namespace) |

The file name is `<name>.<version>.component.xml`, and two components of one repository with the same entity are an error.

## 4. Validation

Validation runs without network access.

| Layer | What it checks |
| :--- | :--- |
| Schema | The IEEE 1685-2022 XSD files published by Accellera (Apache 2.0), packaged unchanged in `src/riscv_tools/ipxact/schemas/1685-2022/` with the NOTICE, read by `xmlschema` |
| Semantic rules | The rules of the table below, which the schema does not express |
| Consistency with the VHDL | The versioned document equals what the VHDL gives (`generate --check`) |

| Rule | Clause | What it checks |
| :--- | :--- | :--- |
| SCR 1.10 | B.2.1 | The document element is a legal type |
| SCR 5.2 | C.6.2 | `parameterId` on a `user` or `generated` parameter |
| SCR 5.13 | C.7 | Value inside `minimum` and `maximum` |
| SCR 5.14 | 6.15.2.2 | A module parameter is valid only inside its instantiation |
| SCR 5.16 | C.21 | The value resolves to the type of the parameter |
| SCR 5.17 | Annex E | Well-formed expression |
| SCR 5.18 | C.9.2 | Every identifier of an expression is a `parameterId` |
| SCR 5.19 | B.2.5 | Expression without circular reference |
| SCR 6.26 | 6.15.1.2 | A component without views has only `phantom` ports |
| C.29.2 | C.29 | A `viewRef` points to a view and each view appears once per `wireTypeDefs` |
| C.7.11 | C.7.11 | A vector limit is a non-negative integer |

The uniqueness of the VLNV (SCR 1.1) comes from the file name, and the existence of referenced documents (SCR 1.2) does not apply to a component that references none.

## 5. Data written by people in `paths.yaml`

```yaml
ipxact:
  exceptions:
    uart_fifo: the o_level port is an integer, with no IP-XACT form

interfaces:
  generic_register:
    buses:
      - name: clock
        contract: clock
        role: target
        ports: {prefix: i_clk}
    unbound:
      i_enable: enable with no bus contract
```

| Key | Content |
| :--- | :--- |
| `ipxact.exceptions` | Entity (or manifest component) with no document, with the reason |
| `interfaces.<entity>.buses` | Bus interfaces: unique `name`, `contract`, `role` (`initiator`, `target`, `system`, `mirroredInitiator`, `mirroredTarget`, `mirroredSystem`, `monitor`) and `ports` by `prefix` or `names` |
| `interfaces.<entity>.unbound` | Ports outside any interface, with the justification |

The `manifest` rule of `check-tree` checks the shape of both sections.

## 6. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_ipxact_sv_expr.py` | The expression evaluator follows SystemVerilog precedence and refuses malformed ones |
| `tests/test_ipxact_flow.py` | Extraction of generics and ports, function expansion, vendor library, generation, `--check`, exceptions and the command line |
| `tests/test_ipxact_semantic.py` | Each semantic rule fails with its number when broken |
| `tests/test_ipxact_manifest.py` | The `paths.yaml` sections, the `manifest` rule of `check-tree` and the vendor library cut |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
