from pathlib import Path

import pytest

from riscv_tools import cli
from riscv_tools.profiles import expand, load_spec

CORE_SPEC = """
base: rv32i
extensions:
  - {name: Zicsr,    generic: has_zicsr}
  - {name: Zifencei, generic: has_zifencei}
  - {name: Zmmul,    generic: has_zmmul}
  - {name: M,        generic: has_m, base_letter: m}
  - {name: Zicclsm,  generic: has_zicclsm, absent_token: nozicclsm}
mutually_exclusive:
  - [M, Zmmul]
requires_any:
  - [Zicsr, Zicclsm]
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "spec.yaml"
    path.write_text(text)
    return path


def test_core_spec_has_eighteen_profiles(tmp_path: Path) -> None:
    """Twelve with Zicclsm plus six without it, which need Zicsr."""
    profiles = expand(load_spec(_write(tmp_path, CORE_SPEC)))
    assert len(profiles) == 18
    assert len({p.name for p in profiles}) == 18


def test_no_profile_breaks_a_rule(tmp_path: Path) -> None:
    for p in expand(load_spec(_write(tmp_path, CORE_SPEC))):
        assert not ({"M", "Zmmul"} <= set(p.extensions))
        assert "Zicsr" in p.extensions or "Zicclsm" in p.extensions


def test_names_keep_the_twelve_profiles_and_mark_a_missing_zicclsm(
    tmp_path: Path,
) -> None:
    names = {p.name for p in expand(load_spec(_write(tmp_path, CORE_SPEC)))}
    assert {
        "rv32i",
        "rv32im",
        "rv32i_zmmul",
        "rv32i_zicsr_zifencei_zmmul",
        "rv32im_zicsr_zifencei",
    } <= names
    assert "rv32im_zicsr_nozicclsm" in names
    assert "rv32i_nozicclsm" not in names


def test_generics_follow_the_extensions(tmp_path: Path) -> None:
    by_name = {p.name: p for p in expand(load_spec(_write(tmp_path, CORE_SPEC)))}
    p = by_name["rv32im_zicsr_nozicclsm"]
    assert p.generics["has_m"] is True
    assert p.generics["has_zmmul"] is False
    assert p.generics["has_zicclsm"] is False
    assert p.generics["has_zicsr"] is True


def test_the_order_of_the_specification_orders_the_profiles(tmp_path: Path) -> None:
    profiles = expand(load_spec(_write(tmp_path, CORE_SPEC)))
    assert [len(p.extensions) for p in profiles] == sorted(
        len(p.extensions) for p in profiles
    )


def test_a_rule_naming_an_unknown_extension_fails(tmp_path: Path) -> None:
    text = CORE_SPEC.replace("[M, Zmmul]", "[M, Zbb]")
    with pytest.raises(ValueError, match="Zbb"):
        load_spec(_write(tmp_path, text))


def test_a_repeated_extension_fails(tmp_path: Path) -> None:
    text = CORE_SPEC.replace(
        "  - {name: Zifencei, generic: has_zifencei}\n",
        "  - {name: Zicsr, generic: has_zicsr}\n",
    )
    with pytest.raises(ValueError, match="repeated"):
        load_spec(_write(tmp_path, text))


def test_a_spec_without_extensions_fails(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="extensions"):
        load_spec(_write(tmp_path, "base: rv32i\n"))


def test_cli_prints_ghdl_generics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = _write(tmp_path, CORE_SPEC)
    args = cli.argparse.Namespace(spec=str(spec), format="generics")
    cli.cmd_profiles(args)
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 18
    expected = (
        "rv32im_zicsr_nozicclsm -ghas_zicsr=true -ghas_zifencei=false -ghas_zmmul=false"
        " -ghas_m=true -ghas_zicclsm=false"
    )
    assert expected in lines
