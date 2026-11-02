"""Verify that a repository follows the layout all of them share.

Each rule looks at one aspect of the tree and returns a list of
problems. A rule applies to some kinds of repository.

| Rule               | What it checks                          |
| ------------------ | --------------------------------------- |
| `standard-files`   | The files every repository of its kind  |
|                    | has                                     |
| `language-pairs`   | `README`, `CONTRIBUTING` and `AUTHORS`  |
|                    | in both languages, and every            |
|                    | `docs/pt-br` file mirrored in `docs/en` |
| `vhdl-location`    | No `.vhd` outside `src/` and            |
|                    | `tests/vhdl/`                           |
| `common-submodule` | Common-Components mounted at            |
|                    | `src/common`                            |
| `folder-names`     | Lowercase folder names without spaces   |
|                    | or accents                              |

The repository's `paths.yaml` may carry a `tree` section to name the
folders that are identifiers of the ISA or of a peripheral and so keep
their capitals (`I`, `Zicsr`, `UART`):

```yaml
tree:
  identifier_folders: [I, M, Zicsr, ISA]
```
"""

import configparser
import os
import re
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, cast

import yaml

KINDS = (
    "common-components",
    "core",
    "memory",
    "peripherals",
    "top",
    "tests",
    "certification",
    "infra",
    "tools",
)
_VHDL_KINDS = frozenset(
    {"common-components", "core", "memory", "peripherals", "top"}
)
_COMMON_MOUNT_KINDS = frozenset({"core", "memory", "peripherals"})
_FORMAL_KINDS = frozenset({"core", "memory", "peripherals", "top"})

STANDARD_FILES = (
    ".gitignore",
    "AUTHORS.md",
    "AUTHORS.en.md",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "CONTRIBUTING.en.md",
    "LICENSE",
    "README.md",
    "README.en.md",
    ".github/workflows",
)
VHDL_FILES = (
    "Makefile",
    "paths.yaml",
    "pyproject.toml",
    "uv.lock",
    "src",
    "tests/python/runner.py",
    "tests/python/tests.json",
    "tests/python/unittests",
)
FORMAL_FILES = ("formal/run.sh",)
_LANGUAGE_PAIRS = ("README", "CONTRIBUTING", "AUTHORS")
_DOCS = Path("docs")
_PT = "pt-br"
_EN = "en"
_COMMON_PATH = "src/common"
_COMMON_REPOSITORY = "Common-Components"
_VHDL_ROOTS = ("src", "tests/vhdl")
_FOLDER_NAME = re.compile(r"[a-z0-9][a-z0-9_.-]*")
_NOT_SOURCES = frozenset(
    {
        "build",
        "sim_build",
        "__pycache__",
        "node_modules",
        "output_files",
        "db",
        "incremental_db",
    }
)

Rule = Callable[[Path, str, dict[str, Any]], list[str]]


def _tree_config(root: Path) -> dict[str, Any]:
    """Read the `tree` section of the repository's `paths.yaml`.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    dict of str to Any
        The section, or an empty mapping when the file or the section
        is absent.
    """
    manifest = root / "paths.yaml"
    if not manifest.is_file():
        return {}
    data = yaml.safe_load(manifest.read_text())
    if not isinstance(data, dict):
        return {}
    section = cast("dict[str, Any]", data).get("tree")
    if not isinstance(section, dict):
        return {}
    return cast("dict[str, Any]", section)


def _directories(root: Path) -> Iterator[Path]:
    """Walk the folders of the repository that belong to it.

    The walk leaves out hidden folders, build output, third-party code
    in `vendor` and any folder that is a repository of its own (a
    submodule), whose layout is checked in its own repository.

    Parameters
    ----------
    root : Path
        The repository root.

    Yields
    ------
    Path
        Each folder, below the root.
    """
    for current, names, _ in os.walk(root):
        here = Path(current)
        names[:] = sorted(
            name
            for name in names
            if not name.startswith(".")
            and name not in _NOT_SOURCES
            and name != "vendor"
            and not (here / name / ".git").exists()
        )
        for name in names:
            yield here / name


def _files(root: Path, suffix: str) -> Iterator[Path]:
    """List the files with a suffix in the folders of the repository.

    Parameters
    ----------
    root : Path
        The repository root.
    suffix : str
        The file name ending, such as `.vhd`.

    Yields
    ------
    Path
        Each file found, including the ones in the root itself.
    """
    for folder in (root, *_directories(root)):
        for entry in sorted(folder.iterdir()):
            if entry.is_file() and entry.name.endswith(suffix):
                yield entry


def _rule_standard_files(
    root: Path, kind: str, _config: dict[str, Any]
) -> list[str]:
    """Report the files every repository of the kind must have.

    Parameters
    ----------
    root : Path
        The repository root.
    kind : str
        The kind of repository.
    _config : dict of str to Any
        The `tree` section; unused by this rule.

    Returns
    -------
    list of str
        One problem for each missing file or folder.
    """
    required: list[str] = list(STANDARD_FILES)
    if kind in _VHDL_KINDS:
        required.extend(VHDL_FILES)
    if kind in _FORMAL_KINDS:
        required.extend(FORMAL_FILES)
    return [
        f"missing {path}" for path in required if not (root / path).exists()
    ]


def _markdown(folder: Path) -> set[str]:
    """List the Markdown files under a folder, relative to it.

    Parameters
    ----------
    folder : Path
        The folder to list.

    Returns
    -------
    set of str
        The relative paths in POSIX form; empty when the folder is
        absent.
    """
    if not folder.is_dir():
        return set()
    return {
        path.relative_to(folder).as_posix() for path in folder.rglob("*.md")
    }


def _rule_language_pairs(
    root: Path, _kind: str, _config: dict[str, Any]
) -> list[str]:
    """Report documents that exist in one language and not in the other.

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
        One problem for each document without its counterpart.
    """
    problems: list[str] = []
    for stem in _LANGUAGE_PAIRS:
        portuguese = (root / f"{stem}.md").is_file()
        english = (root / f"{stem}.en.md").is_file()
        if portuguese != english:
            missing = f"{stem}.en.md" if portuguese else f"{stem}.md"
            problems.append(f"missing {missing}, the pair of its other half")
    portuguese_docs = _markdown(root / _DOCS / _PT)
    english_docs = _markdown(root / _DOCS / _EN)
    problems.extend(
        f"missing {_DOCS / _EN / name}, mirror of {_PT}"
        for name in sorted(portuguese_docs - english_docs)
    )
    problems.extend(
        f"missing {_DOCS / _PT / name}, mirror of {_EN}"
        for name in sorted(english_docs - portuguese_docs)
    )
    return problems


def _rule_vhdl_location(
    root: Path, _kind: str, _config: dict[str, Any]
) -> list[str]:
    """Report VHDL files outside the folders meant for them.

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
        One problem for each `.vhd` outside `src/` and `tests/vhdl/`.
    """
    problems: list[str] = []
    for path in _files(root, ".vhd"):
        relative = path.relative_to(root).as_posix()
        if not any(relative.startswith(f"{base}/") for base in _VHDL_ROOTS):
            problems.append(f"{relative} is outside src/ and tests/vhdl/")
    return problems


def _submodule_paths(root: Path) -> dict[str, str]:
    """Read the submodules a repository declares.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    dict of str to str
        The URL of each submodule, keyed by its path; empty when there
        is no `.gitmodules`.
    """
    gitmodules = root / ".gitmodules"
    if not gitmodules.is_file():
        return {}
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(gitmodules.read_text())
    return {
        parser.get(section, "path"): parser.get(section, "url", fallback="")
        for section in parser.sections()
        if parser.has_option(section, "path")
    }


def _rule_common_submodule(
    root: Path, _kind: str, _config: dict[str, Any]
) -> list[str]:
    """Report a repository that does not mount Common-Components.

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
        One problem when `src/common` is not a Common-Components
        submodule.
    """
    url = _submodule_paths(root).get(_COMMON_PATH)
    if url is None:
        return [f"{_COMMON_PATH} is not declared in .gitmodules"]
    if not url.removesuffix(".git").endswith(_COMMON_REPOSITORY):
        return [f"{_COMMON_PATH} points at {url}, not {_COMMON_REPOSITORY}"]
    return []


def _rule_folder_names(
    root: Path, _kind: str, config: dict[str, Any]
) -> list[str]:
    """Report folders whose names a build tool would split or mangle.

    Quartus (Tcl), GHDL and Make treat a space as a separator, so a
    folder name is lowercase with hyphens. The folders listed under
    `identifier_folders` in `paths.yaml` name the ISA or a peripheral
    and are accepted as they are.

    Parameters
    ----------
    root : Path
        The repository root.
    _kind : str
        The kind of repository; unused by this rule.
    config : dict of str to Any
        The `tree` section, with the optional `identifier_folders`.

    Returns
    -------
    list of str
        One problem for each folder with an unaccepted name.
    """
    listed = config.get("identifier_folders", [])
    identifiers = (
        {str(name) for name in cast("list[Any]", listed)}
        if isinstance(listed, list)
        else set[str]()
    )
    return [
        f"{directory.relative_to(root).as_posix()}: use lowercase letters,"
        " digits and hyphens, with no space or accent"
        for directory in _directories(root)
        if directory.name not in identifiers
        and not _FOLDER_NAME.fullmatch(directory.name)
    ]


_RULES: dict[str, tuple[Rule, frozenset[str]]] = {
    "standard-files": (_rule_standard_files, frozenset(KINDS)),
    "language-pairs": (_rule_language_pairs, frozenset(KINDS)),
    "vhdl-location": (_rule_vhdl_location, _VHDL_KINDS),
    "common-submodule": (_rule_common_submodule, _COMMON_MOUNT_KINDS),
    "folder-names": (_rule_folder_names, _VHDL_KINDS),
}


def rule_names(kind: str) -> list[str]:
    """List the rules that apply to a kind of repository.

    Parameters
    ----------
    kind : str
        One of `KINDS`.

    Returns
    -------
    list of str
        The rule names, in the order they run.

    Raises
    ------
    ValueError
        If the kind is unknown.
    """
    if kind not in KINDS:
        raise ValueError(
            f"unknown kind {kind!r}; use one of {', '.join(KINDS)}"
        )
    return [name for name, (_, kinds) in _RULES.items() if kind in kinds]


def check_tree(
    root: Path, kind: str, only: Sequence[str] | None = None
) -> list[str]:
    """Run the rules of a kind of repository over its tree.

    Parameters
    ----------
    root : Path
        The repository root.
    kind : str
        One of `KINDS`.
    only : sequence of str, optional
        The rules to run; by default, every rule of the kind. A
        repository that has not finished its reorganization names the
        rules it already meets.

    Returns
    -------
    list of str
        One line for each problem, `<rule> <message>`; empty when the
        tree conforms.

    Raises
    ------
    ValueError
        If the kind or a rule name is unknown, or a named rule does not
        apply to the kind.
    """
    available = rule_names(kind)
    selected = available if only is None else list(only)
    for name in selected:
        if name not in available:
            raise ValueError(
                f"rule {name!r} does not apply to {kind}; "
                f"use one of {', '.join(available)}"
            )
    config = _tree_config(root)
    problems: list[str] = []
    for name in selected:
        rule, _ = _RULES[name]
        problems.extend(f"{name} {line}" for line in rule(root, kind, config))
    return problems
