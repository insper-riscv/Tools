"""Check the VHDL files of a repository against the style guide.

The guide is the VHDL part of the Core's `CONTRIBUTING.md`, which every
repository repeats. The files of third parties (`vendor/`) and the IPs
that Quartus generates are left out, because nobody edits them by hand
and they carry the header and the licence of their origin.

| Rule        | What it checks                                      |
| ----------- | --------------------------------------------------- |
| `header`    | Header block of 72 columns at the top               |
| `libraries` | Only `std_logic_1164` and `numeric_std` from IEEE   |
| `component` | No `component`; direct `entity work.x` instances    |
| `port-map`  | Every `port map` association by name                |
| `ports`     | `i_`, `o_` and `io_` prefixes on every port         |
| `docstrings`| A comment above each declaration                    |
| `naming`    | `UPPER_SNAKE_CASE` constants, `_t` types, `u_`      |
|             | instance labels                                     |

The `vhdl_style` section under `tree` in the repository's `paths.yaml`
names more files to leave out, as globs relative to the root:

```yaml
tree:
  vhdl_style:
    exclude: [src/pll/*.vhd]
```
"""

import fnmatch
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from riscv_tools.repo_walk import list_files, tree_config
from riscv_tools.vhdl_style.rules import RULES, make_source

_IP_FOLDERS = frozenset({"cyclone-v"})
_IP_MARKERS = ("megafunction wizard", "altera_mf")


def rule_names() -> list[str]:
    """List the style rules.

    Returns
    -------
    list of str
        The rule names, in the order they run.
    """
    return list(RULES)


def _extra_excludes(root: Path) -> list[str]:
    """Read the globs that `paths.yaml` adds to the exclusions.

    Parameters
    ----------
    root : Path
        The repository root.

    Returns
    -------
    list of str
        The globs, empty when the repository names none.
    """
    section = tree_config(root).get("vhdl_style")
    if not isinstance(section, dict):
        return []
    listed = cast("dict[str, object]", section).get("exclude", [])
    if not isinstance(listed, list):
        return []
    return [str(glob) for glob in cast("list[object]", listed)]


def is_generated_ip(relative: str, text: str) -> bool:
    """Tell a Quartus IP from a file written by hand.

    Parameters
    ----------
    relative : str
        The path relative to the repository root, in POSIX form.
    text : str
        The content of the file.

    Returns
    -------
    bool
        True when the file sits in a `cyclone-v` folder or instantiates
        a Quartus megafunction (`altera_mf`).
    """
    folders = {part.lower() for part in relative.split("/")[:-1]}
    lowered = text.lower()
    return bool(folders & _IP_FOLDERS) or any(
        marker in lowered for marker in _IP_MARKERS
    )


def _file_problems(
    root: Path, path: Path, selected: list[str], excludes: list[str]
) -> list[str]:
    """Run the selected rules over one file.

    Parameters
    ----------
    root : Path
        The repository root.
    path : Path
        The file.
    selected : list of str
        The rules to run.
    excludes : list of str
        The globs of files to leave out, relative to the root.

    Returns
    -------
    list of str
        The violations as `<file>:<line>: <rule> <message>`; empty for
        a file that is left out.
    """
    relative = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    if is_generated_ip(relative, text) or any(
        fnmatch.fnmatch(relative, glob) for glob in excludes
    ):
        return []
    source = make_source(text)
    return [
        f"{relative}:{line}: {name} {message}"
        for name in selected
        for line, message in RULES[name](source)
    ]


def check_vhdl_style(
    root: Path, only: Sequence[str] | None = None
) -> list[str]:
    """Run the style rules over the VHDL files of a repository.

    Parameters
    ----------
    root : Path
        The repository root.
    only : sequence of str, optional
        The rules to run; by default, every rule.

    Returns
    -------
    list of str
        One line for each violation, `<file>:<line>: <rule> <message>`;
        empty when every file conforms.

    Raises
    ------
    ValueError
        If a rule name is unknown.
    """
    selected = list(RULES) if only is None else list(only)
    unknown = [name for name in selected if name not in RULES]
    if unknown:
        raise ValueError(
            f"unknown rule {unknown[0]!r}; use one of {', '.join(RULES)}"
        )
    excludes = _extra_excludes(root)
    problems: list[str] = []
    for path in list_files(root, ".vhd"):
        problems.extend(_file_problems(root, path, selected, excludes))
    return problems
