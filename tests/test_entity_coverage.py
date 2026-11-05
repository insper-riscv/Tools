"""Tests for the entity-coverage and vhdl-style rules of tree_check."""

import json
from pathlib import Path

from support import check_equal, check_false, check_in, check_not_in

from riscv_tools.tree_check import check_tree, opt_in_rules, rule_names


def _write(root: Path, name: str, text: str = "") -> None:
    """Create a file and the folders above it."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _entity(root: Path, name: str, folder: str = "src") -> None:
    """Write a file that declares an entity of the same name."""
    _write(root, f"{folder}/{name}.vhd", f"entity {name} is\nend entity;\n")


def _tests_json(root: Path, entries: dict[str, tuple[str, list[str]]]) -> None:
    """Write `tests.json` from (toplevel, sources) pairs."""
    data = {
        key: {"toplevel": top, "sources": sources}
        for key, (top, sources) in entries.items()
    }
    _write(root, "tests/python/tests.json", json.dumps(data))


def _coverage(root: Path) -> list[str]:
    """Run only the coverage rule."""
    return check_tree(root, "memory", ["entity-coverage"])


def test_the_new_rules_are_opt_in() -> None:
    """They exist for the VHDL kinds but do not run by default."""
    check_in("entity-coverage", opt_in_rules("memory"))
    check_in("vhdl-style", opt_in_rules("core"))
    check_not_in("entity-coverage", rule_names("memory"))
    check_not_in("vhdl-style", rule_names("memory"))
    check_false(opt_in_rules("tools"))


def test_an_entity_with_its_test_passes(tmp_path: Path) -> None:
    """A test with the entity as top level and its file covers it."""
    _entity(tmp_path, "sdram_ctrl")
    _tests_json(tmp_path, {"S": ("sdram_ctrl", ["src/sdram_ctrl.vhd"])})
    check_false(_coverage(tmp_path))


def test_a_testbench_named_after_the_entity_covers_it(
    tmp_path: Path,
) -> None:
    """The top level `<name>_tb` counts as the entity."""
    _entity(tmp_path, "mux_tree")
    _tests_json(tmp_path, {"M": ("mux_tree_tb", ["src/mux_tree.vhd"])})
    check_false(_coverage(tmp_path))


def test_an_entity_without_a_test_is_reported(tmp_path: Path) -> None:
    """A system test that lists the file does not cover the entity."""
    _entity(tmp_path, "sdram_ctrl")
    _entity(tmp_path, "sdram_system", "src/sim")
    _tests_json(
        tmp_path,
        {"S": ("sdram_system", ["src/sdram_ctrl.vhd", "src/sim/s.vhd"])},
    )
    problems = _coverage(tmp_path)
    check_equal(len(problems), 1)
    check_in("sdram_ctrl (src/sdram_ctrl.vhd) has no entry", problems[0])


def test_a_test_must_list_the_file_of_the_entity(tmp_path: Path) -> None:
    """The top level is not enough, the sources must list the file."""
    _entity(tmp_path, "gpio")
    _tests_json(tmp_path, {"G": ("gpio", ["src/other.vhd"])})
    check_in("does not list src/gpio.vhd", _coverage(tmp_path)[0])


def test_models_ips_and_vendor_are_not_rtl(tmp_path: Path) -> None:
    """Simulation models, IPs and vendor code need no test."""
    _entity(tmp_path, "model", "src/sim")
    _entity(tmp_path, "ram", "src/RAM/Cyclone-V")
    _entity(tmp_path, "uart", "src/vendor")
    _tests_json(tmp_path, {})
    check_false(_coverage(tmp_path))


def test_an_exception_needs_a_justification(tmp_path: Path) -> None:
    """An excused entity needs its reason; a stale excuse fails."""
    _entity(tmp_path, "boot_rom_shell")
    _tests_json(tmp_path, {})
    _write(
        tmp_path,
        "paths.yaml",
        "tree:\n  coverage:\n    exceptions:\n"
        "      boot_rom_shell: wraps an IP\n",
    )
    check_false(_coverage(tmp_path))
    _write(
        tmp_path,
        "paths.yaml",
        "tree:\n  coverage:\n    exceptions:\n      boot_rom_shell:\n"
        "      ghost: nothing\n",
    )
    problems = _coverage(tmp_path)
    check_in(
        "entity-coverage exception boot_rom_shell has no justification",
        problems,
    )
    check_in(
        "entity-coverage exception ghost names no entity of src/", problems
    )


def test_a_named_proof_needs_its_file(tmp_path: Path) -> None:
    """Each entity named in `formal` has `formal/<name>.sv`."""
    _entity(tmp_path, "synchronizer")
    _tests_json(tmp_path, {"S": ("synchronizer", ["src/synchronizer.vhd"])})
    _write(
        tmp_path,
        "paths.yaml",
        "tree:\n  coverage:\n    formal: [synchronizer, ghost]\n",
    )
    problems = _coverage(tmp_path)
    check_in(
        "entity-coverage missing formal/synchronizer.sv, the proof of "
        "synchronizer",
        problems,
    )
    check_in("entity-coverage formal ghost names no entity of src/", problems)
    _write(tmp_path, "formal/synchronizer.sv")
    check_equal(len(_coverage(tmp_path)), 1)


def test_vhdl_style_runs_through_check_tree(tmp_path: Path) -> None:
    """Naming the rule reports the violations of the style guide."""
    _write(tmp_path, "src/a.vhd", "entity a is end;\n")
    problems = check_tree(tmp_path, "core", ["vhdl-style"])
    check_equal(len(problems), 1)
    check_in("vhdl-style src/a.vhd:1: header", problems[0])
