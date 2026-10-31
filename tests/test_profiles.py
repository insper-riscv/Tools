"""Tests for profiles."""

import argparse
from pathlib import Path

import pytest

from riscv_tools import cli
from riscv_tools.profiles import expand, load_spec

CORE_SPEC = """
base: rv32i
extensions:
  - {name: Zicclsm,  generic: has_zicclsm}
  - {name: Zicsr,    generic: has_zicsr}
  - {name: Zicntr,   generic: has_zicntr, implies: [has_zicsr]}
  - {name: Zifencei, generic: has_zifencei}
  - {name: Zmmul,    generic: has_zmmul}
  - {name: M,        generic: has_m, base_letter: m}
mutually_exclusive:
  - [M, Zmmul]
  - [Zicsr, Zicntr]
"""

# The thirty-six names of the profile table of the extra plan.
PROFILE_NAMES = [
    "rv32i",
    "rv32i_zifencei",
    "rv32i_zicsr",
    "rv32i_zicsr_zifencei",
    "rv32i_zicntr",
    "rv32i_zicntr_zifencei",
    "rv32i_zicclsm",
    "rv32i_zicclsm_zifencei",
    "rv32i_zicclsm_zicsr",
    "rv32i_zicclsm_zicsr_zifencei",
    "rv32i_zicclsm_zicntr",
    "rv32i_zicclsm_zicntr_zifencei",
    "rv32i_zmmul",
    "rv32i_zifencei_zmmul",
    "rv32i_zicsr_zmmul",
    "rv32i_zicsr_zifencei_zmmul",
    "rv32i_zicntr_zmmul",
    "rv32i_zicntr_zifencei_zmmul",
    "rv32i_zicclsm_zmmul",
    "rv32i_zicclsm_zifencei_zmmul",
    "rv32i_zicclsm_zicsr_zmmul",
    "rv32i_zicclsm_zicsr_zifencei_zmmul",
    "rv32i_zicclsm_zicntr_zmmul",
    "rv32i_zicclsm_zicntr_zifencei_zmmul",
    "rv32im",
    "rv32im_zifencei",
    "rv32im_zicsr",
    "rv32im_zicsr_zifencei",
    "rv32im_zicntr",
    "rv32im_zicntr_zifencei",
    "rv32im_zicclsm",
    "rv32im_zicclsm_zifencei",
    "rv32im_zicclsm_zicsr",
    "rv32im_zicclsm_zicsr_zifencei",
    "rv32im_zicclsm_zicntr",
    "rv32im_zicclsm_zicntr_zifencei",
]


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "spec.yaml"
    path.write_text(text)
    return path


def test_core_spec_has_thirty_six_profiles(tmp_path: Path) -> None:
    """Zicclsm x2, CSRs x3, Zifencei x2 and multiplier x3."""
    profiles = expand(load_spec(_write(tmp_path, CORE_SPEC)))
    assert len(profiles) == 36
    assert len({p.name for p in profiles}) == 36


def test_the_names_are_exactly_the_table_of_the_plan(tmp_path: Path) -> None:
    """The names are exactly the table of the plan."""
    names = {p.name for p in expand(load_spec(_write(tmp_path, CORE_SPEC)))}
    assert names == set(PROFILE_NAMES)


def test_no_profile_breaks_a_rule(tmp_path: Path) -> None:
    """No profile breaks a rule."""
    for p in expand(load_spec(_write(tmp_path, CORE_SPEC))):
        assert not ({"M", "Zmmul"} <= set(p.extensions))
        assert not ({"Zicsr", "Zicntr"} <= set(p.extensions))


def test_a_name_never_cites_zicsr_next_to_zicntr(tmp_path: Path) -> None:
    """A name never cites zicsr next to zicntr."""
    for p in expand(load_spec(_write(tmp_path, CORE_SPEC))):
        if "Zicntr" in p.extensions:
            assert "zicsr" not in p.name


def test_zicntr_turns_zicsr_on(tmp_path: Path) -> None:
    """Zicntr turns zicsr on."""
    by_name = {
        p.name: p for p in expand(load_spec(_write(tmp_path, CORE_SPEC)))
    }
    p = by_name["rv32im_zicclsm_zicntr_zifencei"]
    assert p.generics["has_zicntr"] is True
    assert p.generics["has_zicsr"] is True
    assert p.generics["has_m"] is True
    assert p.generics["has_zmmul"] is False
    q = by_name["rv32i_zicsr"]
    assert (
        q.generics["has_zicntr"] is False and q.generics["has_zicsr"] is True
    )


def test_the_core_without_csrs_and_without_zicclsm_is_valid(
    tmp_path: Path,
) -> None:
    """The core without csrs and without zicclsm is valid."""
    by_name = {
        p.name: p for p in expand(load_spec(_write(tmp_path, CORE_SPEC)))
    }
    p = by_name["rv32i"]
    assert p.generics["has_zicsr"] is False
    assert p.generics["has_zicclsm"] is False


def test_the_order_of_the_specification_orders_the_profiles(
    tmp_path: Path,
) -> None:
    """The order of the specification orders the profiles."""
    profiles = expand(load_spec(_write(tmp_path, CORE_SPEC)))
    assert [len(p.extensions) for p in profiles] == sorted(
        len(p.extensions) for p in profiles
    )


def test_an_absent_token_still_marks_a_missing_extension(
    tmp_path: Path,
) -> None:
    """An absent token still marks a missing extension."""
    text = CORE_SPEC.replace(
        "{name: Zicclsm,  generic: has_zicclsm}",
        "{name: Zicclsm,  generic: has_zicclsm, absent_token: nozicclsm}",
    )
    names = {p.name for p in expand(load_spec(_write(tmp_path, text)))}
    assert "rv32i_nozicclsm" in names
    assert "rv32i" in names, "the plain name is the one with Zicclsm"


def test_a_rule_naming_an_unknown_extension_fails(tmp_path: Path) -> None:
    """A rule naming an unknown extension fails."""
    text = CORE_SPEC.replace("[M, Zmmul]", "[M, Zbb]")
    with pytest.raises(ValueError, match="Zbb"):
        load_spec(_write(tmp_path, text))


def test_a_repeated_extension_fails(tmp_path: Path) -> None:
    """A repeated extension fails."""
    text = CORE_SPEC.replace(
        "  - {name: Zifencei, generic: has_zifencei}\n",
        "  - {name: Zicsr, generic: has_zicsr}\n",
    )
    with pytest.raises(ValueError, match="repeated"):
        load_spec(_write(tmp_path, text))


def test_a_spec_without_extensions_fails(tmp_path: Path) -> None:
    """A spec without extensions fails."""
    with pytest.raises(ValueError, match="extensions"):
        load_spec(_write(tmp_path, "base: rv32i\n"))


def test_cli_prints_ghdl_generics(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cli prints ghdl generics."""
    spec = _write(tmp_path, CORE_SPEC)
    args = argparse.Namespace(spec=str(spec), format="generics")
    cli.cmd_profiles(args)
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 36
    expected = (
        "rv32im_zicclsm_zicntr -ghas_zicclsm=true -ghas_zicsr=true"
        " -ghas_zicntr=true"
        " -ghas_zifencei=false -ghas_zmmul=false -ghas_m=true"
    )
    assert expected in lines


def test_the_command_needs_no_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command needs no config."""
    spec = _write(tmp_path, CORE_SPEC)
    monkeypatch.setattr(
        "sys.argv", ["riscv-tools", "profiles", "--spec", str(spec)]
    )
    cli.main()
    assert len(capsys.readouterr().out.splitlines()) == 36


# The matrix of the core with the event counters: Zihpm joins Zicntr and
# each implies Zicsr.
HPM_SPEC = CORE_SPEC.replace(
    "  - {name: Zifencei,",
    "  - {name: Zihpm,    generic: has_zihpm,  implies: [has_zicsr]}\n"
    "  - {name: Zifencei,",
).replace("  - [Zicsr, Zicntr]\n", "  - [Zicsr, Zicntr]\n  - [Zicsr, Zihpm]\n")


def test_the_matrix_with_zihpm_has_sixty_profiles(tmp_path: Path) -> None:
    """Five states of CSR block give sixty profiles."""
    profiles = expand(load_spec(_write(tmp_path, HPM_SPEC)))
    assert len(profiles) == 60
    assert len({p.name for p in profiles}) == 60


def test_zihpm_turns_zicsr_on_and_never_cites_it(tmp_path: Path) -> None:
    """A profile with Zihpm has Zicsr on and no zicsr in its name."""
    for p in expand(load_spec(_write(tmp_path, HPM_SPEC))):
        if "Zihpm" in p.extensions:
            assert p.generics["has_zicsr"] is True
            assert "zicsr" not in p.name


def test_zicntr_and_zihpm_come_together_in_the_spec_order(
    tmp_path: Path,
) -> None:
    """Zicntr and Zihpm together are named zicntr_zihpm."""
    names = {p.name for p in expand(load_spec(_write(tmp_path, HPM_SPEC)))}
    assert "rv32im_zicclsm_zicntr_zihpm_zifencei" in names
    assert "rv32i_zihpm_zifencei_zmmul" in names
    assert not any("zihpm_zicntr" in n for n in names)
