"""Tests for the IP-XACT sections of paths.yaml and the vendor stub."""

from pathlib import Path

from support import check, check_equal, check_in, check_not_in

from riscv_tools.ipxact.manifest import (
    exceptions,
    load_interfaces,
    manifest_problems,
)
from riscv_tools.ipxact.stub import entity_only, needs_vendor_library
from riscv_tools.tree_check.manifest import rule_manifest

GOOD = """\
ipxact:
  exceptions:
    sdram_ctrl: the limit calls a function
interfaces:
  generic_register:
    buses:
      - name: clock
        contract: clock
        role: target
        ports: {prefix: i_clk}
      - name: data
        contract: data
        role: initiator
        ports: {names: [i_d, o_d]}
    unbound:
      i_enable: strobe with no contract
"""


def _paths(tmp_path: Path, text: str) -> Path:
    """Write a paths.yaml."""
    (tmp_path / "paths.yaml").write_text(text)
    return tmp_path


def test_sections_are_read(tmp_path: Path) -> None:
    """Exceptions, buses and unbound ports come out as written."""
    root = _paths(tmp_path, GOOD)
    found_exceptions, problems_exceptions = exceptions(root)
    check_equal(found_exceptions, {"sdram_ctrl": "the limit calls a function"})
    check_equal(problems_exceptions, [])
    found, problems = load_interfaces(root)
    check_equal(problems, [])
    entity = found["generic_register"]
    check_equal([bus.name for bus in entity.buses], ["clock", "data"])
    check_equal(entity.buses[0].prefix, "i_clk")
    check_equal(entity.buses[1].names, ("i_d", "o_d"))
    check_equal(entity.unbound, {"i_enable": "strobe with no contract"})


def test_absent_sections_are_fine(tmp_path: Path) -> None:
    """A repository with neither section has no problem."""
    check_equal(manifest_problems(_paths(tmp_path, "repository: X\n")), [])
    check_equal(manifest_problems(tmp_path / "nowhere"), [])


def test_malformed_sections_are_reported(tmp_path: Path) -> None:
    """Every malformation names the place it is in."""
    bad = """\
ipxact:
  exceptions:
    a: ""
interfaces:
  e:
    buses:
      - {name: x, contract: c, role: nonsense, ports: {}}
      - {name: x, contract: c, role: target, ports: {prefix: p}}
    unbound: [oops]
  f: 3
"""
    text = " | ".join(manifest_problems(_paths(tmp_path, bad)))
    for part in (
        "ipxact.exceptions.a",
        "`role` is one of",
        "`ports` has a `prefix` or `names`",
        "interface x is declared twice",
        "interfaces.e.unbound",
        "interfaces.f",
    ):
        check_in(part, text)


def test_tree_manifest_rule_reports_them(tmp_path: Path) -> None:
    """The manifest rule of check-tree includes the IP-XACT sections."""
    root = _paths(
        tmp_path,
        "provides:\n  a:\n    sources: [src/a.vhd]\ninterfaces:\n  e: 3\n",
    )
    (root / "src").mkdir()
    (root / "src" / "a.vhd").write_text("")
    found = rule_manifest(root, "core", {})
    check(any(line.startswith("interfaces.e") for line in found), str(found))


def test_vendor_stub() -> None:
    """The stub keeps the entity and the line numbers."""
    text = (
        "library ieee;\nlibrary altera_mf;\nuse altera_mf.all;\n"
        "entity e is\n  port (i : in bit);\nend entity;\n"
        "architecture rtl of e is\nbegin\nend architecture;\n"
    )
    check(needs_vendor_library(text))
    check_equal(needs_vendor_library("library ieee;\nuse ieee.all;\n"), False)
    reduced = entity_only(text)
    check_equal(len(reduced.split("\n")), len(text.split("\n")))
    check_in("-- library altera_mf;", reduced)
    check_in("-- use altera_mf.all;", reduced)
    check_in("end entity;", reduced)
    check_not_in("architecture", reduced)
