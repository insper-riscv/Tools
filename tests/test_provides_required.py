"""Tests for the `provides-required` rule of `check-tree`."""

from pathlib import Path

from support import check_equal, check_false, check_in

from riscv_tools.tree_check import KINDS, check_tree

COMPONENT = "provides:\n  a:\n    sources: [src/a.vhd]\n"


def _repository(root: Path, paths: str) -> None:
    """Lay out one source file and a `paths.yaml`."""
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "a.vhd").write_text("")
    (root / "paths.yaml").write_text(paths)


def _required(root: Path, kind: str) -> list[str]:
    """Run only the `provides-required` rule."""
    return check_tree(root, kind, ["provides-required"])


def test_a_vhdl_repository_without_provides_fails(tmp_path: Path) -> None:
    """Losing the section fails every VHDL kind."""
    _repository(tmp_path, "tree:\n  identifier_folders: []\n")
    for kind in ("common-components", "core", "memory", "peripherals", "top"):
        problems = _required(tmp_path, kind)
        check_equal(len(problems), 1)
        check_in("provides-required paths.yaml declares no", problems[0])


def test_a_missing_paths_yaml_fails_too(tmp_path: Path) -> None:
    """Without the file there is no section either."""
    check_equal(len(_required(tmp_path, "core")), 1)


def test_a_repository_with_provides_passes(tmp_path: Path) -> None:
    """Declaring the section satisfies the rule."""
    _repository(tmp_path, COMPONENT)
    for kind in KINDS:
        check_false(_required(tmp_path, kind))


def test_a_malformed_section_is_left_to_the_manifest_rule(
    tmp_path: Path,
) -> None:
    """A section that exists is not reported as missing."""
    _repository(tmp_path, "provides:\n  a: {}\n")
    check_false(_required(tmp_path, "core"))
    check_in("manifest", check_tree(tmp_path, "core", ["manifest"])[0])


def test_the_tree_section_can_opt_out(tmp_path: Path) -> None:
    """`require_provides: false` lets a VHDL repository go without."""
    _repository(tmp_path, "tree:\n  require_provides: false\n")
    check_false(_required(tmp_path, "memory"))


def test_the_tree_section_can_ask_for_other_kinds(tmp_path: Path) -> None:
    """The other kinds are exempt unless `require_provides: true`."""
    _repository(tmp_path, "tree:\n  identifier_folders: []\n")
    check_false(_required(tmp_path, "tools"))
    _repository(tmp_path, "tree:\n  require_provides: true\n")
    check_equal(len(_required(tmp_path, "tools")), 1)


def test_a_value_that_is_not_a_boolean_is_reported(tmp_path: Path) -> None:
    """Only true or false is accepted."""
    _repository(tmp_path, "tree:\n  require_provides: yes please\n")
    check_equal(
        _required(tmp_path, "core"),
        ["provides-required tree.require_provides is true or false"],
    )


def test_the_default_run_includes_the_rule(tmp_path: Path) -> None:
    """A plain `check-tree` catches the loss without `--only`."""
    _repository(tmp_path, "tree:\n  identifier_folders: []\n")
    problems = check_tree(tmp_path, "memory")
    check_in(
        "provides-required",
        " ".join(problem.split()[0] for problem in problems),
    )
