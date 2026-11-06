"""Tests for the `purity` rule of `check-tree`."""

import argparse
from pathlib import Path

import pytest
from support import check_equal, check_false, check_in, check_not_in

from riscv_tools import cli
from riscv_tools.cli.tree_cmd import cmd_check_tree
from riscv_tools.tree_check import check_tree, opt_in_rules, rule_names
from riscv_tools.tree_check import purity as purity_module


def _write(root: Path, relative: str, text: str) -> None:
    """Write one file, creating its folders."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _purity(root: Path, kind: str = "memory") -> list[str]:
    """Run only the `purity` rule."""
    return check_tree(root, kind, ["purity"])


def test_a_portable_tree_passes(tmp_path: Path) -> None:
    """A file that names no board, family or primitive is clean."""
    _write(tmp_path, "src/ram.vhd", "-- a RAM that obeys the contract\n")
    check_equal(_purity(tmp_path), [])


@pytest.mark.parametrize(
    "term",
    [
        "altsyncram",
        "altsyncram_inst",
        "altpll",
        "altera_pll",
        "altera_mf",
        "sld_virtual_jtag",
        "intended_device_family",
    ],
)
def test_a_vendor_primitive_outside_a_vendor_folder_fails(
    tmp_path: Path, term: str
) -> None:
    """Each primitive of the data is reported with file and line."""
    _write(tmp_path, "src/ram.vhd", f"entity ram is\nu: {term}\n")
    problems = _purity(tmp_path)
    check_equal(len(problems), 1)
    check_in("purity src/ram.vhd:2:", problems[0])
    check_in(term.split("_", maxsplit=1)[0], problems[0])


@pytest.mark.parametrize(
    "spelling", ["DE0-CV", "de0_cv", "de0cv", "DE10-Lite", "DE2-115"]
)
def test_a_board_name_fails_in_any_spelling(
    tmp_path: Path, spelling: str
) -> None:
    """Case, hyphen, underscore and no separator are the same board."""
    _write(tmp_path, "src/top.vhd", f"-- for the {spelling} board\n")
    problems = _purity(tmp_path)
    check_equal(len(problems), 1)
    check_in("boards:", problems[0])


def test_a_family_a_device_and_an_idcode_fail(tmp_path: Path) -> None:
    """The family, the part number and the JTAG IDCODE are names too."""
    _write(
        tmp_path,
        "src/top.vhd",
        '-- Cyclone V\nconstant c : string := "5CEBA4F23C7N";\n'
        '-- MAX 10\nconstant i : std_logic_vector := x"02B050DD";\n',
    )
    groups = [line.split(":")[2].strip() for line in _purity(tmp_path)]
    check_equal(sorted(groups), ["devices", "families", "families", "idcodes"])


def test_a_vendor_folder_is_exempt_at_any_depth(tmp_path: Path) -> None:
    """`altera/` and `boards/` may name vendor, family and board."""
    text = "u: altsyncram\n-- Cyclone V in the DE0-CV\n"
    _write(tmp_path, "src/block_ram/altera/ram.vhd", text)
    _write(tmp_path, "src/boards/de0-cv/top.vhd", text)
    _write(tmp_path, "src/Altera/ram.vhd", text)
    check_equal(_purity(tmp_path), [])
    _write(tmp_path, "src/alteras/ram.vhd", text)
    check_equal(len(_purity(tmp_path)), 3)


def test_a_word_that_only_looks_like_a_term_passes(tmp_path: Path) -> None:
    """The boundary keeps Portuguese and unrelated words out."""
    _write(
        tmp_path,
        "src/a.vhd",
        "-- a alteração altera o valor do codede0 e do reade0cv2\n"
        "-- fale-de0 cyclonic\n",
    )
    check_equal(_purity(tmp_path), [])


def test_only_the_listed_suffixes_are_read(tmp_path: Path) -> None:
    """Documents and board files are not RTL sources."""
    _write(tmp_path, "docs/pt-br/a.md", "DE0-CV altsyncram\n")
    _write(tmp_path, "src/top.qsf", "set_global_assignment DE0-CV\n")
    _write(tmp_path, "src/pll.v", "altera_pll p();\n")
    problems = _purity(tmp_path)
    check_equal(len(problems), 1)
    check_in("src/pll.v:1:", problems[0])


def test_the_first_line_and_the_count_are_reported(tmp_path: Path) -> None:
    """Many hits of one term in a file make one problem."""
    _write(tmp_path, "src/a.vhd", "x\naltpll\naltpll\nx\naltpll\n")
    check_equal(
        _purity(tmp_path),
        [
            "purity src/a.vhd:2: primitives:altpll* (3x) "
            "outside the vendor folders"
        ],
    )


def test_an_exception_excuses_a_file_a_folder_or_a_pattern(
    tmp_path: Path,
) -> None:
    """The three forms of path cover the files they match."""
    for name in ("a.vhd", "legacy/b.vhd", "gen/top_1.vhd", "c.vhd"):
        _write(tmp_path, f"src/{name}", "altpll\n")
    _write(
        tmp_path,
        "paths.yaml",
        "tree:\n  purity:\n    exceptions:\n"
        "      src/a.vhd: wrapper pending\n"
        "      src/legacy: old tops\n"
        "      src/gen/top_*.vhd: generated\n",
    )
    problems = _purity(tmp_path)
    check_equal(len(problems), 1)
    check_in("src/c.vhd", problems[0])


def test_an_exception_needs_a_justification_and_a_file(
    tmp_path: Path,
) -> None:
    """An exception without text or without a hit is a problem."""
    _write(tmp_path, "src/a.vhd", "altpll\n")
    _write(
        tmp_path,
        "paths.yaml",
        "tree:\n  purity:\n    exceptions:\n"
        "      src/a.vhd:\n"
        "      src/gone.vhd: moved\n",
    )
    problems = _purity(tmp_path)
    check_in("purity exception src/a.vhd has no justification", problems)
    check_in("purity exception src/gone.vhd excuses no file", problems)
    check_equal(len(problems), 2)


def test_the_repository_adds_terms_folders_and_suffixes(
    tmp_path: Path,
) -> None:
    """`paths.yaml` extends the data without replacing it."""
    _write(tmp_path, "src/a.vhd", "-- my-board\n")
    _write(tmp_path, "src/vendor-x/b.vhd", "altpll my-board\n")
    _write(tmp_path, "src/c.tcl", "my-board\n")
    check_equal(len(_purity(tmp_path)), 1)
    _write(
        tmp_path,
        "paths.yaml",
        "tree:\n  purity:\n    terms:\n      boards: [my-board]\n"
        "    vendor_folders: [vendor-x]\n    suffixes: [.tcl]\n",
    )
    problems = _purity(tmp_path)
    check_equal(len(problems), 2)
    check_in("src/a.vhd", problems[0])
    check_in("src/c.tcl", problems[1])
    _write(tmp_path, "src/d.vhd", "altpll\n")
    check_equal(len(_purity(tmp_path)), 3)


def test_the_terms_come_from_the_data_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changing `purity.yaml` changes the verdict, not the code."""
    data = tmp_path / "data.yaml"
    data.write_text(
        "vendor_folders: [maker]\nsuffixes: [.vhd]\n"
        "terms:\n  boards: [zebra]\nexceptions:\n  src/z.vhd: shared\n"
    )
    monkeypatch.setattr(purity_module, "_DEFAULTS", data)
    repo = tmp_path / "repo"
    _write(repo, "src/a.vhd", "altpll zebra\n")
    _write(repo, "src/maker/b.vhd", "zebra\n")
    _write(repo, "src/z.vhd", "zebra\n")
    problems = _purity(repo)
    check_equal(len(problems), 1)
    check_in("boards:zebra", problems[0])
    check_not_in("altpll", problems[0])


def test_a_submodule_is_left_to_its_own_repository(tmp_path: Path) -> None:
    """The walk skips the folders the `.gitmodules` declares."""
    _write(tmp_path, "src/common/a.vhd", "altpll\n")
    _write(
        tmp_path,
        ".gitmodules",
        '[submodule "c"]\n\tpath = src/common\n\turl = x/Common-Components\n',
    )
    check_equal(_purity(tmp_path), [])


def test_the_rule_is_opt_in_and_for_the_vhdl_kinds(tmp_path: Path) -> None:
    """The default run leaves it out; non-VHDL kinds reject it."""
    _write(tmp_path, "src/a.vhd", "altpll\n")
    check_not_in("purity", rule_names("memory"))
    check_in("purity", opt_in_rules("top"))
    check_false(check_tree(tmp_path, "memory", ["manifest"]))
    with pytest.raises(ValueError, match="does not apply to tools"):
        check_tree(tmp_path, "tools", ["purity"])


def test_cmd_check_tree_runs_the_rule(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command exits 1 with a `TREE purity` line, or 0 if clean."""
    _write(tmp_path, "src/a.vhd", "altpll\n")
    args = argparse.Namespace(
        kind="memory", only="purity", root=str(tmp_path), config=None
    )
    with pytest.raises(SystemExit) as failed:
        cmd_check_tree(args)
    check_equal(failed.value.code, 1)
    check_in("TREE purity src/a.vhd:1:", capsys.readouterr().err)
    (tmp_path / "src/a.vhd").write_text("clean\n")
    cmd_check_tree(args)
    check_in("rules purity", capsys.readouterr().out)
    monkeypatch.setattr(
        "sys.argv",
        [
            "riscv-tools",
            "--root",
            str(tmp_path),
            "check-tree",
            "--kind",
            "memory",
            "--only",
            "purity",
        ],
    )
    cli.main()
