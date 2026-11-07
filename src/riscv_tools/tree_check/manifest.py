"""Read and check the `provides` manifest of a repository.

The `paths.yaml` of a VHDL repository may declare which files make up
each component and which components it needs:

```yaml
repository: Memory   # optional; by default, the name of the folder
provides:
  onchip_ram:
    requires: [Common-Components/utils, ram_simulation]
    sources: [src/RAM/SoC/onchip_ram_port.vhd]
    needs: [block_ram]   # optional: the board resources it depends on
```

The `sources` follow the order GHDL analyzes them. A name in `requires`
without a prefix is a component of the same repository;
`<repository>/<component>` names one of another repository. The
`manifest` rule of `check-tree` runs only on repositories that declare
`provides`; `riscv-tools sources` reads the manifests to emit the list
of files of a target. The `provides-required` rule fails a repository of
a VHDL kind that declares none, unless its `tree` section sets
`require_provides: false`; any other kind can ask for it with
`require_provides: true`.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from riscv_tools.repo_walk import list_files

REQUIRED_KINDS = frozenset(
    {"common-components", "core", "memory", "peripherals", "top"}
)

# Os tipos de recurso de placa que `needs` de um componente aceita.
NEED_TYPES = frozenset(
    {
        "block_ram",
        "sdram",
        "sram",
        "nor",
        "onchip_flash",
        "serial_flash",
        "vjtag",
    }
)


@dataclass(frozen=True)
class Component:
    """A group of source files that is built and reused as a unit.

    Parameters
    ----------
    sources : tuple of str
        The files of the component, relative to the repository root and
        in the order they are analyzed.
    requires : tuple of str
        The components it needs, as written in the manifest.
    needs : tuple of str, optional
        The board resource types it depends on (`NEED_TYPES`).
    """

    sources: tuple[str, ...]
    requires: tuple[str, ...]
    needs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Provides:
    """The `provides` manifest of one repository.

    Parameters
    ----------
    repository : str
        The name other manifests use to reach this repository.
    components : dict of str to Component
        The components, keyed by name.
    """

    repository: str
    components: dict[str, Component]


def _strings(value: Any) -> list[str] | None:
    """Read a YAML value that must be a list of strings.

    Parameters
    ----------
    value : Any
        The parsed value.

    Returns
    -------
    list of str or None
        The strings; None when the value is not a list of strings.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        return None
    items = cast("list[Any]", value)
    if not all(isinstance(item, str) for item in items):
        return None
    return cast("list[str]", items)


def _read_component(
    name: str, raw: Any, problems: list[str]
) -> Component | None:
    """Read one component, reporting what is malformed.

    Parameters
    ----------
    name : str
        The component name.
    raw : Any
        The parsed value of the component.
    problems : list of str
        Receives one line for each malformation.

    Returns
    -------
    Component or None
        The component; None when it is malformed.
    """
    if not isinstance(raw, dict):
        problems.append(f"{name}: a component is a mapping")
        return None
    body = cast("dict[str, Any]", raw)
    sources = _strings(body.get("sources"))
    requires = _strings(body.get("requires"))
    needs = _strings(body.get("needs"))
    if not sources and not requires:
        problems.append(f"{name}: `sources` is a non-empty list of paths")
    if requires is None:
        problems.append(f"{name}: `requires` is a list of names")
    if needs is None:
        problems.append(f"{name}: `needs` is a list of resource types")
    else:
        problems.extend(
            f"{name}: `needs` {item} is not one of "
            f"{', '.join(sorted(NEED_TYPES))}"
            for item in needs
            if item not in NEED_TYPES
        )
    if not sources or requires is None or needs is None:
        return None
    return Component(tuple(sources), tuple(requires), tuple(needs))


def _raw(root: Path) -> tuple[Any, Any]:
    """Read the raw `repository` and `provides` values of `paths.yaml`.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    tuple of (Any, Any)
        The parsed values; None for each one that is absent.
    """
    manifest = root / "paths.yaml"
    if not manifest.is_file():
        return None, None
    data = yaml.safe_load(manifest.read_text())
    if not isinstance(data, dict):
        return None, None
    top = cast("dict[str, Any]", data)
    return top.get("repository"), top.get("provides")


def load_provides(
    root: Path, default_name: str | None = None
) -> tuple[Provides | None, list[str]]:
    """Read the `provides` section of the repository's `paths.yaml`.

    Parameters
    ----------
    root : Path
        The repository root.
    default_name : str, optional
        The repository name when `paths.yaml` has no `repository`; by
        default, the name of the root folder.

    Returns
    -------
    tuple of (Provides or None, list of str)
        The manifest, None when the repository declares none or it is
        too malformed to use, and one line for each malformation.
    """
    repository, raw = _raw(root)
    if raw is None:
        return None, []
    if not isinstance(raw, dict) or not raw:
        return None, ["provides is a mapping of components"]
    problems: list[str] = []
    components: dict[str, Component] = {}
    for name, body in cast("dict[Any, Any]", raw).items():
        component = _read_component(str(name), body, problems)
        if component is not None:
            components[str(name)] = component
    if problems:
        return None, problems
    name = repository if isinstance(repository, str) else default_name
    return Provides(name or root.name, components), []


def _reaches_itself(
    components: dict[str, Component], start: str, prefix: str
) -> bool:
    """Tell whether a component requires itself, directly or not.

    Parameters
    ----------
    components : dict of str to Component
        The components of the repository.
    start : str
        The component to follow from.
    prefix : str
        The repository prefix removed from the dependency names.

    Returns
    -------
    bool
        True when the requirements lead back to `start`.
    """
    stack = [dep.removeprefix(prefix) for dep in components[start].requires]
    seen: set[str] = set()
    while stack:
        name = stack.pop()
        if name == start:
            return True
        if name in seen or name not in components:
            continue
        seen.add(name)
        stack.extend(
            dep.removeprefix(prefix) for dep in components[name].requires
        )
    return False


def _cycle(components: dict[str, Component], own: str) -> list[str]:
    """Find the dependency cycles among the components of a repository.

    Parameters
    ----------
    components : dict of str to Component
        The components of the repository.
    own : str
        The name of the repository, to recognize its prefixed names.

    Returns
    -------
    list of str
        One problem for each component that is part of a cycle, directly
        or through others.
    """
    prefix = f"{own}/"
    return [
        f"{start}: is part of a requires cycle"
        for start in sorted(components)
        if _reaches_itself(components, start, prefix)
    ]


def _file_problems(
    root: Path, provides: Provides
) -> tuple[list[str], set[str]]:
    """Check the files the components list.

    Parameters
    ----------
    root : Path
        The repository root.
    provides : Provides
        The manifest.

    Returns
    -------
    tuple of (list of str, set of str)
        The problems (missing files, files in two components) and the
        set of listed files.
    """
    problems: list[str] = []
    owner: dict[str, str] = {}
    for name, component in provides.components.items():
        for path in component.sources:
            if not (root / path).is_file():
                problems.append(f"{name}: {path} does not exist")
            elif path in owner and owner[path] != name:
                problems.append(
                    f"{path} is listed by {owner[path]} and by {name}"
                )
            owner.setdefault(path, name)
    return problems, set(owner)


def rule_manifest(
    root: Path, _kind: str, _config: dict[str, Any]
) -> list[str]:
    """Report a `provides` manifest that does not match the tree.

    Parameters
    ----------
    root : Path
        The repository root.
    _kind : str
        The kind of repository; unused by this rule.
    _config : dict of str to Any
        The `tree` section; unused by this rule.

    Returns
    -------
    list of str
        One problem for each malformation, missing file, `.vhd` of
        `src/` listed by no component, unknown dependency of the
        repository itself and dependency cycle. Empty when the
        repository declares no `provides`.
    """
    provides, problems = load_provides(root)
    if provides is None:
        return problems
    file_problems, listed = _file_problems(root, provides)
    problems.extend(file_problems)
    problems.extend(
        f"{path.relative_to(root).as_posix()} is listed by no component"
        for path in list_files(root, ".vhd", "src")
        if path.relative_to(root).as_posix() not in listed
    )
    prefix = f"{provides.repository}/"
    for name, component in provides.components.items():
        problems.extend(
            f"{name}: requires {dep}, which is not a component here"
            for dep in component.requires
            if ("/" not in dep or dep.startswith(prefix))
            and dep.removeprefix(prefix) not in provides.components
        )
    problems.extend(_cycle(provides.components, provides.repository))
    return problems


def rule_provides_required(
    root: Path, kind: str, config: dict[str, Any]
) -> list[str]:
    """Report a repository that must declare `provides` and does not.

    A repository of a VHDL kind must declare the section, so that a
    merge or a rewrite of `paths.yaml` that drops it fails the check
    instead of silently turning the `manifest` rule off. The `tree`
    section decides the other cases with `require_provides`.

    Parameters
    ----------
    root : Path
        The repository root.
    kind : str
        The kind of repository; the VHDL kinds require `provides` by
        default.
    config : dict of str to Any
        The `tree` section, with the optional `require_provides`.

    Returns
    -------
    list of str
        One problem when the section is required and absent; a section
        that exists but is malformed is the `manifest` rule's business.
    """
    required = config.get("require_provides", kind in REQUIRED_KINDS)
    if required is not True:
        if required is not False:
            return ["tree.require_provides is true or false"]
        return []
    if _raw(root)[1] is not None:
        return []
    return [
        "paths.yaml declares no `provides`; this repository must list its"
        " components there (`tree.require_provides: false` opts out)"
    ]
