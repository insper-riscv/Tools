# `sources`

Prints the ordered list of the files of a target, read from the `provides` manifests of the repositories. The source lists of the `config*.yaml`, of `tests.json` and of the Quartus project repeat the same paths in several places, and adding a file meant editing all of them. With the manifest, each file is declared once in the repository that owns it, and this module builds the list of any target from it.

## Resolution

The target is a component, written as `<repository>/<component>`; a name without a prefix is a component of the repository at the root. The output has the components of `requires` before the target, depth first and in the order the manifest lists them, and then the `sources` of the component itself in the declared order. No file appears twice, and the paths come out relative to the root, also for files of repositories mounted below it.

The manifests read are the one of the root itself and the ones of the repositories mounted below it: the submodules of `.gitmodules` and `src/common`. A repository seen twice keeps the first folder found. The files of a submodule never come from the folder listing of the root, only from the manifest of the submodule itself, and a `requires: <repository>/<component>` follows into that manifest when the other repository declares `provides`. The manifest format is in [tree_check](tree_check.md).

## Errors

The command exits with status 2 and a `sources:` line when a manifest is malformed, when the repository or the component of a target or of a `requires` is not found, and when the requirements form a cycle.

## Tests

| Test | What it verifies |
| :--- | :--- |
| `tests/test_manifest_sources.py::test_sources_orders_dependencies_first` | The requirements of another repository come before the target. |
| `tests/test_manifest_sources.py::test_sources_rejects_unknown_targets` | A missing component, repository or manifest fails. |
| `tests/test_manifest_sources.py::test_the_repository_name_defaults_to_the_folder` | Without `repository`, the root folder gives the name. |
| `tests/test_manifest_sources.py::test_the_subcommand_prints_and_fails` | The command prints one path per line and exits with 2 on an error. |

## Usage

```bash
uv run riscv-tools --root <repository> sources core
uv run riscv-tools --root <repository> sources Core/core Memory/cache
```

It needs no `--config`.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
