"""Tests for `sources` over a top that mounts the other repositories."""

from pathlib import Path

from support import check_equal

from riscv_tools.sources import ordered_sources

GITMODULES = """[submodule "Common-Components"]
\tpath = Common-Components
\turl = https://github.com/insper-riscv/Common-Components.git
[submodule "Core"]
\tpath = Core
\turl = https://github.com/insper-riscv/Core.git
[submodule "Memory"]
\tpath = Memory
\turl = https://github.com/insper-riscv/Memory.git
"""
COMMON = (
    "repository: Common-Components\nprovides:\n"
    "  utils:\n    sources: [src/utils.vhd]\n"
)
CORE = (
    "repository: Core\nprovides:\n"
    "  core:\n    sources: [src/core.vhd]\n"
    "    requires: [Common-Components/utils]\n"
)
MEMORY = (
    "repository: Memory\nprovides:\n"
    "  ram:\n    sources: [src/ram.vhd]\n"
    "    requires: [Common-Components/utils]\n"
)
TOP = (
    "repository: Top\nprovides:\n"
    "  sim_top:\n    sources: [src/sim_top.vhd]\n"
    "    requires: [Core/core, Memory/ram, Common-Components/utils]\n"
)


def _write(path: Path, text: str = "") -> None:
    """Create a file and the folders above it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _repository(root: Path, paths: str, source: str) -> None:
    """Lay out a `paths.yaml` and its one source file."""
    _write(root / "paths.yaml", paths)
    _write(root / "src" / source)


def test_a_top_resolves_requires_across_the_submodules(
    tmp_path: Path,
) -> None:
    """Each shared file comes once, before the ones that use it."""
    _write(tmp_path / ".gitmodules", GITMODULES)
    _repository(tmp_path, TOP, "sim_top.vhd")
    _repository(tmp_path / "Common-Components", COMMON, "utils.vhd")
    _repository(tmp_path / "Core", CORE, "core.vhd")
    _repository(tmp_path / "Memory", MEMORY, "ram.vhd")
    check_equal(
        ordered_sources(tmp_path, ["sim_top"]),
        [
            "Common-Components/src/utils.vhd",
            "Core/src/core.vhd",
            "Memory/src/ram.vhd",
            "src/sim_top.vhd",
        ],
    )


def test_a_leaf_reaches_the_common_components_at_src_common(
    tmp_path: Path,
) -> None:
    """A repository that mounts the Common-Components finds it there."""
    _write(
        tmp_path / ".gitmodules",
        GITMODULES.replace("path = Common-Components", "path = src/common"),
    )
    _repository(tmp_path, CORE, "core.vhd")
    _repository(tmp_path / "src" / "common", COMMON, "utils.vhd")
    check_equal(
        ordered_sources(tmp_path, ["core"]),
        ["src/common/src/utils.vhd", "src/core.vhd"],
    )
