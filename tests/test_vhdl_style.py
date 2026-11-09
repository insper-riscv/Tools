"""Tests for vhdl_style: the VSG with the local rules of the project."""

import argparse
from pathlib import Path

import pytest
from support import check, check_equal, check_false, check_in

from riscv_tools import cli
from riscv_tools.cli.vhdl_style_cmd import (
    cmd_check_vhdl_style,
    cmd_vhdl_files,
    cmd_vsg_config,
    cmd_vsg_rules,
)
from riscv_tools.vhdl_style import (
    BOARD_CONFIG,
    CONFIG,
    LOCAL_RULES,
    check_vhdl_style,
    vhdl_files,
)

BAR = "-- " + "=" * 77

HEADER = f"""{BAR}
-- Multiplexador de duas entradas
--
-- Seleciona i_d0 ou i_d1 conforme i_sel.
{BAR}
"""

GOOD = (
    HEADER
    + """
library ieee;
use ieee.std_logic_1164.all;

entity mux_2x1 is
    generic (
        -- Largura em bits dos barramentos
        DATA_WIDTH : natural := 32
    );
    port (
        -- Entrada selecionada quando i_sel vale '0'
        i_d0  : in    std_logic_vector(DATA_WIDTH - 1 downto 0);
        -- Bit seletor
        i_sel : in    std_logic;
        -- Saída multiplexada
        o_out : out   std_logic_vector(DATA_WIDTH - 1 downto 0)
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
)

# The signals of `sram_ctrl_tb.vhd` of the Memory, as `vsg --fix` leaves
# them (one declaration for each line, only the first with its comment).
FIXED_SIGNALS = """
architecture tb of sram_ctrl_tb is

    -- Pinos de controle.
    signal ce_n : std_logic;
    signal oe_n : std_logic;
    signal we_n : std_logic;
    signal lb_n : std_logic;
    signal ub_n : std_logic;

begin
end architecture tb;
"""

# The same signals before the fix: one comment for the five names.
ORIGINAL_SIGNALS = """
architecture tb of sram_ctrl_tb is

    -- Pinos de controle.
    signal ce_n, oe_n, we_n, lb_n, ub_n : std_logic;

begin
end architecture tb;
"""

# The signals of `soc.vhd` of the Insper-RISC-V after the same fix.
FIXED_IRQ_SIGNALS = """
architecture rtl of soc is

    -- Interrupção de software de máquina (MSIP), saída do CLINT.
    signal irq_software   : std_logic := '0';
    -- As três linhas de interrupção como o núcleo as recebe.
    signal irq_timer_q    : std_logic := '0';
    signal irq_software_q : std_logic := '0';
    signal irq_external_q : std_logic := '0';
    -- Interrupção externa de máquina (MEIP), saída do PLIC.
    signal irq_external   : std_logic := '0';

begin
end architecture rtl;
"""

ENTITY = """
library ieee;
use ieee.std_logic_1164.all;

entity e is
end entity e;
"""


def _write(root: Path, name: str, text: str) -> None:
    """Create a VHDL file below the root."""
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _violations(tmp_path: Path, text: str) -> list[str]:
    """Run the gate over a single source file."""
    _write(tmp_path, "src/x.vhd", text)
    return check_vhdl_style(tmp_path)


def _lines_of(problems: list[str], rule: str) -> list[int]:
    """List the lines where a rule reports, in the syntastic output."""
    return [
        int(problem.split("(")[1].split(")")[0])
        for problem in problems
        if f"){rule} -- " in problem
    ]


def _rule_lines(tmp_path: Path, text: str, rule: str) -> list[int]:
    """Run the gate over a source file and list where a rule reports."""
    return _lines_of(_violations(tmp_path, text), rule)


def _line_of(text: str, needle: str) -> int:
    """Find the 1-based line of the first line that has the text."""
    for number, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return number
    raise AssertionError(needle)


def test_a_conforming_file_has_no_violation(tmp_path: Path) -> None:
    """A file that follows the guide passes every rule of the gate."""
    check_false(_violations(tmp_path, GOOD))


def test_header_is_required(tmp_path: Path) -> None:
    """A file without the header block is reported on line 1."""
    problems = _violations(tmp_path, GOOD.removeprefix(HEADER))
    check_equal(_lines_of(problems, "header_900"), [1])
    check_in("cabeçalho", problems[0])


def test_header_needs_description_and_closing_line(tmp_path: Path) -> None:
    """A header without text or without the closing bar fails."""
    body = GOOD.removeprefix(HEADER)
    check_equal(
        _rule_lines(tmp_path, f"{BAR}\n{BAR}\n{body}", "header_900"),
        [1],
    )
    check_equal(
        _rule_lines(tmp_path, f"{BAR}\n-- texto\n{body}", "header_900"),
        [1],
    )


def test_header_has_no_minimum_width(tmp_path: Path) -> None:
    """A header of 40 columns passes, and so does one of 100."""
    body = GOOD.removeprefix(HEADER)
    for width in (40, 100):
        line = "-- " + "=" * (width - 3)
        problems = _violations(tmp_path, f"{line}\n-- texto\n{line}\n{body}")
        check_equal(_lines_of(problems, "header_900"), [])


def test_libraries_allow_only_the_two_packages(tmp_path: Path) -> None:
    """Another package of IEEE fails, and `numeric_std` passes."""
    text = GOOD.replace(
        "use ieee.std_logic_1164.all;",
        "use ieee.std_logic_1164.all;\nuse ieee.numeric_std.all;",
    )
    check_equal(_rule_lines(tmp_path, text, "library_900"), [])
    text = GOOD.replace(
        "use ieee.std_logic_1164.all;",
        "use ieee.std_logic_1164.all;\nuse ieee.std_logic_arith.all;",
    )
    problems = _violations(tmp_path, text)
    check_equal(
        _lines_of(problems, "library_900"),
        [_line_of(text, "std_logic_arith")],
    )
    check_in("ieee.std_logic_arith", problems[0])


def test_component_is_forbidden_but_not_in_comments(tmp_path: Path) -> None:
    """A component declaration fails; the word in a comment does not."""
    check_equal(_rule_lines(tmp_path, GOOD, "component_900"), [])
    text = GOOD.replace(
        "    -- Sinal interno\n",
        "    component other is\n    end component other;\n"
        "    -- Sinal interno\n",
    )
    check_equal(
        _rule_lines(tmp_path, text, "component_900"),
        [_line_of(text, "component other")],
    )


def test_component_has_no_exception_for_generated_wrappers(
    tmp_path: Path,
) -> None:
    """A wrapper of a PLL is reported like any other file."""
    text = GOOD.replace(
        "    -- Sinal interno\n",
        "    component pll_0002 is\n    end component pll_0002;\n"
        "    -- Sinal interno\n",
    )
    _write(tmp_path, "src/pll/pll.vhd", text)
    problems = check_vhdl_style(tmp_path)
    check_equal(
        _lines_of(problems, "component_900"),
        [_line_of(text, "component pll_0002")],
    )
    check_in("src/pll/pll.vhd", problems[0])


def test_component_instance_is_forbidden(tmp_path: Path) -> None:
    """The instance `u_x : component x` fails as well."""
    text = GOOD.replace("u_sub : entity work.other", "u_sub : component other")
    check_equal(
        _rule_lines(tmp_path, text, "component_900"),
        [_line_of(text, "component other")],
    )


def test_port_map_must_associate_by_name(tmp_path: Path) -> None:
    """Each positional association of a `port map` fails."""
    text = GOOD.replace("i_a => i_d0,", "i_d0,")
    check_equal(
        _rule_lines(tmp_path, text, "port_map_900"),
        [_line_of(text, "i_d0,")],
    )
    text = GOOD.replace(
        "i_a => i_d0,\n            o_b => o_out", "i_d0, o_out"
    )
    line = _line_of(text, "i_d0, o_out")
    check_equal(_rule_lines(tmp_path, text, "port_map_900"), [line, line])


def test_docstrings_are_needed_above_each_declaration(
    tmp_path: Path,
) -> None:
    """A missing comment, a trailing comment and a separator fail."""
    text = GOOD.replace("    -- Sinal interno\n", "")
    check_equal(
        _rule_lines(tmp_path, text, "docstring_900"),
        [_line_of(text, "signal sel")],
    )
    text = GOOD.replace(
        "    -- Sinal interno\n    signal sel : std_logic;",
        "    signal sel : std_logic; -- Sinal interno",
    )
    check_equal(
        _rule_lines(tmp_path, text, "docstring_900"),
        [_line_of(text, "signal sel")],
    )
    text = GOOD.replace("    -- Sinal interno\n", f"    {BAR}\n")
    check_equal(
        _rule_lines(tmp_path, text, "docstring_900"),
        [_line_of(text, "signal sel")],
    )


def test_docstrings_cover_generics_and_ports(tmp_path: Path) -> None:
    """Every generic and port needs its own comment."""
    text = GOOD.replace("        -- Largura em bits dos barramentos\n", "")
    check_equal(
        _rule_lines(tmp_path, text, "docstring_900"),
        [_line_of(text, "DATA_WIDTH :")],
    )
    text = GOOD.replace("        -- Bit seletor\n", "")
    check_equal(
        _rule_lines(tmp_path, text, "docstring_900"),
        [_line_of(text, "i_sel :")],
    )


def test_docstrings_skip_subprogram_parameters(tmp_path: Path) -> None:
    """The parameters of a function are not declarations."""
    text = GOOD.replace(
        "    -- Sinal interno\n",
        "    -- Soma um\n    function inc(x : natural) return natural is\n"
        "    begin\n        return x + 1;\n    end function inc;\n"
        "    -- Sinal interno\n",
    )
    check_equal(_rule_lines(tmp_path, text, "docstring_900"), [])


def test_real_memory_signals_before_the_fix_pass(tmp_path: Path) -> None:
    """One comment for five names is a single declaration."""
    problems = _violations(tmp_path, HEADER + ENTITY + ORIGINAL_SIGNALS)
    check_equal(_lines_of(problems, "docstring_900"), [])


def test_real_memory_signals_after_the_fix_fail(tmp_path: Path) -> None:
    """The four names that the fix split off lose their comment."""
    problems = _violations(tmp_path, HEADER + ENTITY + FIXED_SIGNALS)
    lines = _lines_of(problems, "docstring_900")
    check_equal(len(lines), 4)
    check_equal(lines, list(range(lines[0], lines[0] + 4)))
    check_in("signal", problems[0])


def test_real_insper_signals_after_the_fix_fail(tmp_path: Path) -> None:
    """Three signals of the SoC lose their comment; two keep it."""
    problems = _violations(tmp_path, HEADER + ENTITY + FIXED_IRQ_SIGNALS)
    check_equal(len(_lines_of(problems, "docstring_900")), 2)


def test_ports_and_names_come_from_the_vsg_rules(tmp_path: Path) -> None:
    """Prefixes, constants, types and labels use the VSG rules."""
    text = GOOD.replace("i_sel", "sel_i").replace("WIDTH_MAX", "width_max")
    text = text.replace("state_t", "state").replace("u_sub", "sub")
    problems = _violations(tmp_path, text)
    for rule in ("port_600", "constant_004", "type_600", "instantiation_601"):
        check(_lines_of(problems, rule), rule)


def test_vendor_code_is_left_out(tmp_path: Path) -> None:
    """The files of `vendor/` are not listed."""
    _write(tmp_path, "src/uart/vendor/x.vhd", "entity x is end;\n")
    _write(tmp_path, "src/a.vhd", GOOD)
    check_equal(vhdl_files(tmp_path), ["src/a.vhd"])


def test_quartus_megafunction_files_are_listed(tmp_path: Path) -> None:
    """A file that uses `altera_mf` is listed like any other."""
    _write(tmp_path, "src/a.vhd", GOOD)
    _write(tmp_path, "src/b.vhd", "library altera_mf;\n" + GOOD)
    _write(tmp_path, "src/c.vhd", "-- Megafunction Wizard\n" + GOOD)
    check_equal(vhdl_files(tmp_path), ["src/a.vhd", "src/b.vhd", "src/c.vhd"])


def test_instance_by_component_name_is_forbidden(tmp_path: Path) -> None:
    """The instance `u_x : name` with no `entity` is a component."""
    text = GOOD.replace("u_sub : entity work.other", "u_sub : altsyncram")
    check_equal(
        _rule_lines(tmp_path, text, "component_900"),
        [_line_of(text, "altsyncram")],
    )


def test_paths_yaml_can_leave_out_more_files(tmp_path: Path) -> None:
    """The globs of `tree.vhdl_style.exclude` are not listed."""
    _write(tmp_path, "src/gerado/a.vhd", "entity a is end;\n")
    _write(tmp_path, "src/b.vhd", GOOD)
    _write(
        tmp_path,
        "paths.yaml",
        "tree:\n  vhdl_style:\n    exclude: [src/gerado/*.vhd]\n",
    )
    check_equal(vhdl_files(tmp_path), ["src/b.vhd"])


def test_the_scope_is_src_and_the_tests_folder(tmp_path: Path) -> None:
    """Only `src/**` and `tests/vhdl/*.vhd` are listed."""
    for name in (
        "src/a/b/c.vhd",
        "tests/vhdl/t.vhd",
        "tests/vhdl/deep/t.vhd",
        "other/x.vhd",
        "x.vhd",
    ):
        _write(tmp_path, name, GOOD)
    check_equal(vhdl_files(tmp_path), ["src/a/b/c.vhd", "tests/vhdl/t.vhd"])


def test_submodules_are_left_out(tmp_path: Path) -> None:
    """The files of `src/common` (a submodule) are not listed."""
    _write(tmp_path, "src/common/a.vhd", GOOD)
    _write(tmp_path, "src/b.vhd", GOOD)
    _write(
        tmp_path,
        ".gitmodules",
        '[submodule "common"]\n\tpath = src/common\n\turl = x\n',
    )
    check_equal(vhdl_files(tmp_path), ["src/b.vhd"])


def test_board_files_are_listed_apart(tmp_path: Path) -> None:
    """The top-levels in `cyclone-v/` come only with `board`."""
    _write(tmp_path, "src/a.vhd", GOOD)
    _write(tmp_path, "src/Cyclone-V/top.vhd", GOOD)
    check_equal(vhdl_files(tmp_path), ["src/a.vhd"])
    check_equal(vhdl_files(tmp_path, board=True), ["src/Cyclone-V/top.vhd"])


def test_board_files_follow_the_rules_but_not_the_naming(
    tmp_path: Path,
) -> None:
    """A board top-level keeps its pin names but needs a header."""
    body = GOOD.removeprefix(HEADER)
    pins = body.replace("i_sel", "KEY").replace("WIDTH_MAX", "width_max")
    _write(tmp_path, "src/cyclone-v/top.vhd", HEADER + pins)
    check_false(check_vhdl_style(tmp_path))
    _write(tmp_path, "src/cyclone-v/top.vhd", pins)
    check_equal(_lines_of(check_vhdl_style(tmp_path), "header_900"), [1])


def test_the_gate_accepts_what_only_the_full_check_rejects(
    tmp_path: Path,
) -> None:
    """A long line passes the gate and fails `full`."""
    text = GOOD.replace("    -- Sinal interno\n", "    -- " + "x" * 130 + "\n")
    _write(tmp_path, "src/x.vhd", text)
    check_false(check_vhdl_style(tmp_path))
    problems = check_vhdl_style(tmp_path, full=True)
    check_in("length_001", "\n".join(problems))


def test_the_packaged_data_exist() -> None:
    """The configuration, the layer and the local rules are files."""
    check(CONFIG.is_file())
    check(BOARD_CONFIG.is_file())
    names = {path.name for path in LOCAL_RULES.glob("*_900.py")}
    check_equal(
        names,
        {
            "header_900.py",
            "library_900.py",
            "component_900.py",
            "port_map_900.py",
            "docstring_900.py",
        },
    )


def test_local_rule_messages_are_in_portuguese(tmp_path: Path) -> None:
    """The messages cite the section of the CONTRIBUTING."""
    text = GOOD.replace("i_a => i_d0,", "i_d0,")
    problems = _violations(tmp_path, text)
    check_in("CONTRIBUTING", problems[0])


def _args(root: Path, **extra: object) -> argparse.Namespace:
    """Build the namespace of a vhdl subcommand."""
    return argparse.Namespace(root=str(root), full=False, board=False, **extra)


def test_cmd_check_vhdl_style_exit_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command prints OK, or exits with 1 listing the violations."""
    _write(tmp_path, "src/x.vhd", GOOD)
    cmd_check_vhdl_style(_args(tmp_path))
    check_in("vhdl style OK", capsys.readouterr().out)
    _write(tmp_path, "src/x.vhd", ENTITY)
    with pytest.raises(SystemExit) as raised:
        cmd_check_vhdl_style(_args(tmp_path))
    check_equal(raised.value.code, 1)
    check_in("header_900", capsys.readouterr().err)


def test_the_vsg_subcommands_print_paths_and_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The subcommands print the config, the rules and the file list."""
    cmd_vsg_config(_args(tmp_path))
    check_equal(capsys.readouterr().out.strip(), str(CONFIG))
    cmd_vsg_config(argparse.Namespace(board=True))
    check_equal(capsys.readouterr().out.strip(), str(BOARD_CONFIG))
    cmd_vsg_rules(_args(tmp_path))
    check_equal(capsys.readouterr().out.strip(), str(LOCAL_RULES))
    _write(tmp_path, "src/x.vhd", GOOD)
    cmd_vhdl_files(_args(tmp_path))
    check_equal(capsys.readouterr().out.strip(), "src/x.vhd")


def test_the_subcommands_are_registered_without_a_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The subcommands run with no `--config`."""
    _write(tmp_path, "src/x.vhd", GOOD)
    for command in ("vsg-config", "vsg-rules", "vhdl-files"):
        monkeypatch.setattr(
            "sys.argv", ["riscv-tools", "--root", str(tmp_path), command]
        )
        cli.main()
    check_in("src/x.vhd", capsys.readouterr().out)
