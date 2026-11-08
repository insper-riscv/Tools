"""Tests of the `needs` key of the `provides` manifest."""

from pathlib import Path

from support import check, check_equal

from riscv_tools.sources import closure_needs
from riscv_tools.tree_check.manifest import load_provides

MANIFEST = """repository: Top
provides:
  top:
    sources: [a.vhd]
    requires: [leaf, other]
    needs: [sdram]
  leaf:
    sources: [b.vhd]
    needs: [block_ram, nor]
  other:
    sources: [c.vhd]
  unused:
    sources: [d.vhd]
    needs: [serial_flash]
"""


def _tree(root: Path, manifest: str) -> None:
    """Lay out a manifest and the empty sources it lists."""
    (root / "paths.yaml").write_text(manifest)
    for name in "abcd":
        (root / f"{name}.vhd").write_text("")


def test_needs_of_the_closure_are_the_union(tmp_path: Path) -> None:
    """Only the components the target reaches contribute."""
    _tree(tmp_path, MANIFEST)
    check_equal(
        closure_needs(tmp_path, ["top"]), ["block_ram", "nor", "sdram"]
    )
    check_equal(closure_needs(tmp_path, ["other"]), [])


def test_needs_default_to_empty(tmp_path: Path) -> None:
    """A component without `needs` keeps the older manifests valid."""
    _tree(tmp_path, MANIFEST)
    provides, problems = load_provides(tmp_path)
    check_equal(problems, [])
    if provides is None:
        raise AssertionError("the manifest should load")
    check_equal(provides.components["other"].needs, ())


def test_an_unknown_need_is_a_manifest_problem(tmp_path: Path) -> None:
    """The types are a closed set, so a typo cannot go unnoticed."""
    _tree(tmp_path, MANIFEST.replace("[sdram]", "[sdramm]"))
    provides, problems = load_provides(tmp_path)
    check(provides is None)
    check_equal(
        problems,
        [
            "top: `needs` sdramm is not one of block_ram, nor, onchip_flash,"
            " sdram, serial_flash, sram, vjtag"
        ],
    )


def test_needs_must_be_a_list(tmp_path: Path) -> None:
    """A scalar `needs` is refused with the other malformations."""
    _tree(tmp_path, MANIFEST.replace("[sdram]", "sdram"))
    _, problems = load_provides(tmp_path)
    check_equal(problems, ["top: `needs` is a list of resource types"])
