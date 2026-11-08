"""Tests for vhdl_style."""

import argparse
from pathlib import Path

import pytest
from support import check_equal, check_false, check_in, check_not_in

from riscv_tools import cli
from riscv_tools.cli.vhdl_style_cmd import cmd_check_vhdl_style
from riscv_tools.vhdl_style import check_vhdl_style, rule_names

BAR = "-- " + "=" * 77

GOOD = f"""{BAR}
-- Multiplexador de duas entradas
--
-- Seleciona i_d0 ou i_d1 conforme i_sel.
{BAR}

library ieee;
use ieee.std_logic_1164.all;

entity mux_2x1 is
    generic(
        -- Largura em bits dos barramentos
        data_width : natural := 32
    );
    port(
        -- Entrada selecionada quando i_sel vale '0'
        i_d0  : in  std_logic_vector(data_width - 1 downto 0);
        -- Bit seletor
        i_sel : in  std_logic;
        -- Saída multiplexada
        o_out : out std_logic_vector(data_width - 1 downto 0)
    );
end entity mux_2x1;

architecture rtl of mux_2x1 is
    -- Constante de teste
    constant WIDTH_MAX : natural := 64;
    -- Tipo de teste
    type state_t is (S_A, S_B);
    -- Sinal interno
    signal sel : std_logic;
begin
    -- A palavra component aparece só neste comentário.
    u_sub : entity work.other
        port map (
            i_a => i_d0,
            o_b => o_out
        );
end architecture rtl;
"""


def _write(root: Path, name: str, text: str) -> None:
    """Create a VHDL file below the root."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _violations(tmp_path: Path, text: str, rule: str) -> list[str]:
    """Run one rule over a single file."""
    _write(tmp_path, "src/x.vhd", text)
    return check_vhdl_style(tmp_path, [rule])


def test_a_conforming_file_has_no_violation(tmp_path: Path) -> None:
    """A file that follows the guide passes every rule."""
    _write(tmp_path, "src/mux_2x1.vhd", GOOD)
    check_false(check_vhdl_style(tmp_path))


def test_header_is_required(tmp_path: Path) -> None:
    """A file without the header block is reported on line 1."""
    problems = _violations(tmp_path, "library ieee;\n", "header")
    check_equal(len(problems), 1)
    check_in("src/x.vhd:1: header", problems[0])


def test_header_needs_description_and_closing_line(tmp_path: Path) -> None:
    """A header with no description or no closing bar is reported."""
    check_equal(len(_violations(tmp_path, f"{BAR}\n{BAR}\n", "header")), 1)
    check_equal(len(_violations(tmp_path, f"{BAR}\n-- texto\n", "header")), 1)


def test_header_has_no_minimum_width(tmp_path: Path) -> None:
    """A header of 40 columns passes, as do the ones of 80."""
    short = "-- " + "=" * 37
    text = f"{short}\n-- texto\n{short}\n"
    check_equal(_violations(tmp_path, text, "header"), [])
    wide = f"{BAR}\n-- texto\n{BAR}\n"
    check_equal(_violations(tmp_path, wide, "header"), [])


def test_libraries_allow_only_the_two_packages(tmp_path: Path) -> None:
    """Any other IEEE package is reported."""
    text = "use ieee.numeric_std.all;\nuse ieee.std_logic_unsigned.all;\n"
    problems = _violations(tmp_path, text, "libraries")
    check_equal(len(problems), 1)
    check_in("std_logic_unsigned", problems[0])


def test_component_is_forbidden_but_not_in_comments(tmp_path: Path) -> None:
    """A `component` is reported, a comment that names it is not."""
    text = "-- component\ncomponent x is\nend component;\n"
    problems = _violations(tmp_path, text, "component")
    check_equal(len(problems), 2)
    check_in("src/x.vhd:2:", problems[0])


def test_port_map_must_associate_by_name(tmp_path: Path) -> None:
    """A positional association in a `port map` is reported."""
    text = "u_x : entity work.x\n  port map (\n    i_a => a,\n    b\n  );\n"
    problems = _violations(tmp_path, text, "port-map")
    check_equal(len(problems), 1)
    check_in("src/x.vhd:4:", problems[0])


def test_ports_need_the_prefix_of_their_mode(tmp_path: Path) -> None:
    """Each port wears `i_`, `o_` or `io_` by its mode."""
    text = (
        "entity e is\n  port(\n    -- a\n    clk : in std_logic;\n"
        "    -- b\n    o_q, y : out std_logic;\n    -- c\n"
        "    io_d : inout std_logic\n  );\nend entity;\n"
    )
    problems = _violations(tmp_path, text, "ports")
    check_equal(len(problems), 2)
    check_in("clk must start with i_", problems[0])
    check_in("y must start with o_", problems[1])


def test_docstrings_are_needed_above_each_declaration(
    tmp_path: Path,
) -> None:
    """A declaration needs its own comment on the line above."""
    text = (
        "architecture a of e is\n"
        "  -- documentado\n  signal ok : std_logic;\n"
        "  signal bare : std_logic;\n"
        "  -- ----------------\n  signal separator : std_logic;\n"
        "  constant INLINE : natural := 1; -- no final da linha\n"
        "begin\n"
        "  process\n    variable v : natural;\n  begin\n  end process;\n"
        "end architecture;\n"
    )
    problems = _violations(tmp_path, text, "docstrings")
    names = " ".join(problems)
    check_not_in("signal ok", names)
    for expected in ("bare", "separator", "INLINE", "variable v"):
        check_in(expected, names)


def test_docstrings_cover_generics_and_skip_subprogram_parameters(
    tmp_path: Path,
) -> None:
    """Generics need a comment; function parameters are skipped."""
    text = (
        "entity e is\n  generic(\n    width : natural := 1\n  );\n"
        "end entity;\n"
        "-- f\nfunction f(constant n : natural) return natural;\n"
    )
    problems = _violations(tmp_path, text, "docstrings")
    check_equal(len(problems), 1)
    check_in("generic width", problems[0])


def test_naming_of_constants_types_and_labels(tmp_path: Path) -> None:
    """Constants, types and labels follow their conventions."""
    text = (
        "-- c\nconstant mid : natural := 1;\n"
        "-- t\ntype node is (A, B);\n"
        "-- s\nsubtype word_t is natural;\n"
        "ICACHE : entity work.icache\n  port map (i_a => a);\n"
    )
    problems = _violations(tmp_path, text, "naming")
    check_equal(len(problems), 3)


def test_vendor_code_and_quartus_ips_are_left_out(tmp_path: Path) -> None:
    """Third party code and generated IPs are not checked."""
    bad = "entity e is end;\n"
    _write(tmp_path, "src/vendor/uart.vhd", bad)
    _write(tmp_path, "src/RAM/Cyclone-V/ram.vhd", bad)
    _write(tmp_path, "src/pll.vhd", "library altera_mf;\n" + bad)
    _write(tmp_path, "src/hand.vhd", bad)
    problems = check_vhdl_style(tmp_path, ["header"])
    check_equal(len(problems), 1)
    check_in("src/hand.vhd", problems[0])


def test_paths_yaml_can_leave_out_more_files(tmp_path: Path) -> None:
    """The globs of `tree.vhdl_style.exclude` are left out."""
    _write(tmp_path, "src/gen/a.vhd", "entity e is end;\n")
    _write(tmp_path, "src/b.vhd", "entity e is end;\n")
    (tmp_path / "paths.yaml").write_text(
        "tree:\n  vhdl_style:\n    exclude: ['src/gen/*.vhd']\n"
    )
    problems = check_vhdl_style(tmp_path, ["header"])
    check_equal(len(problems), 1)
    check_in("src/b.vhd", problems[0])


def test_literals_and_comments_do_not_count_as_code(tmp_path: Path) -> None:
    """A keyword in a string, a character or a comment is ignored."""
    text = (
        '-- c\nconstant TEXT : string := "component -- x";\n'
        "-- c\nconstant BIT_ONE : std_logic := '1'; -- component\n"
    )
    check_false(_violations(tmp_path, text, "component"))
    check_false(_violations(tmp_path, text, "naming"))


def test_an_unknown_rule_is_an_error(tmp_path: Path) -> None:
    """A rule name that does not exist raises."""
    with pytest.raises(ValueError, match="unknown rule"):
        check_vhdl_style(tmp_path, ["nothing"])
    check_in("docstrings", rule_names())


def test_cmd_check_vhdl_style_exit_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command prints OK, or exits 1 listing, or 2 on a bad rule."""
    _write(tmp_path, "src/mux_2x1.vhd", GOOD)
    args = argparse.Namespace(only=None, root=str(tmp_path), config=None)
    cmd_check_vhdl_style(args)
    check_in("vhdl style OK", capsys.readouterr().out)
    _write(tmp_path, "src/bad.vhd", "entity e is end;\n")
    with pytest.raises(SystemExit) as failed:
        cmd_check_vhdl_style(args)
    check_equal(failed.value.code, 1)
    check_in("STYLE src/bad.vhd:1: header", capsys.readouterr().err)
    bad = argparse.Namespace(only="nothing", root=str(tmp_path), config=None)
    with pytest.raises(SystemExit) as unknown:
        cmd_check_vhdl_style(bad)
    check_equal(unknown.value.code, 2)


def test_the_subcommand_is_registered_without_a_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`riscv-tools check-vhdl-style` runs without `--config`."""
    _write(tmp_path, "src/mux_2x1.vhd", GOOD)
    monkeypatch.setattr(
        "sys.argv",
        ["riscv-tools", "--root", str(tmp_path), "check-vhdl-style"],
    )
    cli.main()
    check_in("vhdl style OK", capsys.readouterr().out)
