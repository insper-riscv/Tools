"""Tests for the extraction, generation and check of IP-XACT files."""

import shutil
import sys
from pathlib import Path

import pytest
from support import check, check_equal, check_in, check_not_in

from riscv_tools import cli
from riscv_tools.ipxact import core
from riscv_tools.ipxact.extract import extract

needs_ghdl = pytest.mark.skipif(
    shutil.which("ghdl") is None, reason="ghdl not installed"
)

PACKAGE = """\
-- =====================================================================
-- Pacote de teste
-- =====================================================================
library ieee;
use ieee.std_logic_1164.all;

package demo_pkg is
  -- Largura da palavra.
  constant XLEN : natural := 32;
  -- Seleciona entre dois inteiros.
  function pick(c : boolean; a : integer; b : integer) return integer;
  -- Logaritmo de base 2 arredondado para cima.
  function log2_ceil(arg : positive) return natural;
  -- Metade, arredondada para baixo.
  function half(x : natural) return natural;
  -- Matriz de palavras.
  type word_array_t is array (natural range <>) of std_logic_vector;
end package;

package body demo_pkg is
  function pick(c : boolean; a : integer; b : integer) return integer is
  begin
    if c then
      return a;
    else
      return b;
    end if;
  end function;

  function log2_ceil(arg : positive) return natural is
    variable result : natural := 0;
  begin
    while (2 ** result) < arg loop
      result := result + 1;
    end loop;
    return result;
  end function;

  function half(x : natural) return natural is
  begin
    if x < 2 then
      return 0;
    end if;
    return x / 2;
  end function;
end package body;
"""
REGISTER = """\
-- =====================================================================
-- Registrador de teste
-- =====================================================================
library ieee;
use ieee.std_logic_1164.all;
use work.demo_pkg.all;

entity demo_reg is
  generic (
    -- Largura do dado.
    width     : positive range 1 to 64 := 8;
    -- Profundidade.
    depth     : natural := 16;
    -- Habilita o reset.
    has_reset : boolean := true;
    -- Valor inicial.
    init      : std_logic_vector(7 downto 0) := x"A5";
    -- Nome da instancia.
    label_id  : string := "NO"
  );
  port (
    -- Clock.
    i_clk  : in  std_logic;
    -- Dado de entrada.
    i_d    : in  std_logic_vector(width - 1 downto 0);
    -- Endereco.
    i_addr : in  std_logic_vector(log2_ceil(depth) - 1 downto 0);
    -- Metade alta.
    o_hi   : out std_logic_vector(half(width) downto 0);
    -- Palavras.
    o_arr  : out word_array_t(pick(has_reset, 3, 1) downto 0)(XLEN-1 downto 0)
  );
end entity;

architecture rtl of demo_reg is
begin
end architecture;
"""
VENDOR = """\
-- =====================================================================
-- Bloco de fornecedor
-- =====================================================================
library ieee;
use ieee.std_logic_1164.all;
library altera_mf;
use altera_mf.altera_mf_components.all;

entity demo_vendor is
  port (
    -- Clock.
    i_clk : in std_logic
  );
end entity;

architecture rtl of demo_vendor is
begin
  u_ram : altsyncram port map (clock0 => i_clk);
end architecture;
"""
INTEGER_PORT = """\
-- =====================================================================
-- Bloco com porta inteira
-- =====================================================================
entity demo_int is
  port (
    -- Contagem.
    o_count : out natural range 0 to 7
  );
end entity;
"""
MANIFEST = """\
repository: Demo
provides:
  base:
    requires: []
    sources: [src/demo_pkg.vhd]
  blocks:
    requires: [base]
    sources: [src/demo_reg.vhd, src/demo_vendor.vhd]
"""


def _repo(root: Path, extra: str = "", manifest: str = MANIFEST) -> Path:
    """Lay out a small repository with three entities."""
    (root / "src").mkdir(parents=True)
    (root / "src" / "demo_pkg.vhd").write_text(PACKAGE)
    (root / "src" / "demo_reg.vhd").write_text(REGISTER)
    (root / "src" / "demo_vendor.vhd").write_text(VENDOR)
    (root / "paths.yaml").write_text(manifest + extra)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.2.3"\n'
    )
    return root


@needs_ghdl
def test_extract_translates_generics_and_ports(tmp_path: Path) -> None:
    """Generics become parameters and limits become expressions."""
    result = extract(_repo(tmp_path))
    check_equal(result.failures, {})
    entities = {item.entity.name: item.entity for item in result.found}
    check_equal(sorted(entities), ["demo_reg", "demo_vendor"])
    generics = {g.name: g for g in entities["demo_reg"].generics}
    check_equal(generics["width"].default, "8")
    check_equal(
        (generics["width"].minimum, generics["width"].maximum), (1, 64)
    )
    check_equal(generics["depth"].minimum, 0)
    check_equal(generics["has_reset"].default, "1")
    check_equal(generics["init"].default, "8'hA5")
    check_equal(generics["label_id"].default, "NO")
    check_equal(generics["width"].description, "Largura do dado.")
    ports = {p.name: p for p in entities["demo_reg"].ports}
    check_equal(ports["i_d"].vectors, (("(width - 1)", "0"),))
    check_equal(ports["i_addr"].vectors, (("($clog2(depth) - 1)", "0"),))
    check_equal(ports["o_arr"].vectors[1], ("31", "0"))
    check_equal(ports["o_arr"].type_name, "word_array_t")
    check_equal(ports["o_arr"].type_definition, "work.demo_pkg.all")
    check_in("(has_reset ? 3 : 1)", ports["o_arr"].vectors[0][0])


@needs_ghdl
def test_vendor_library_is_reduced_to_the_entity(tmp_path: Path) -> None:
    """A file that needs a vendor library is read by its entity only."""
    result = extract(_repo(tmp_path))
    names = [item.entity.name for item in result.found]
    check_in("demo_vendor", names)


@needs_ghdl
def test_generate_writes_valid_documents(tmp_path: Path) -> None:
    """The documents validate against the schema and the rules."""
    root = _repo(tmp_path)
    planned = core.plan(root)
    check_equal(planned.problems, [])
    names = core.write(root, planned.documents)
    check_equal(
        names,
        [
            "demo_reg.1.2.3.component.xml",
            "demo_vendor.1.2.3.component.xml",
        ],
    )
    check_equal(core.validate(root), [])
    check_equal(core.check(root), [])
    text = (root / "ipxact" / names[0]).read_text()
    check_in("<ipxact:vendor>insper.edu.br</ipxact:vendor>", text)
    check_in("<ipxact:library>demo</ipxact:library>", text)


@needs_ghdl
def test_check_finds_a_stale_document(tmp_path: Path) -> None:
    """A change in the VHDL makes the stored document differ."""
    root = _repo(tmp_path)
    core.write(root, core.plan(root).documents)
    source = root / "src" / "demo_reg.vhd"
    source.write_text(source.read_text().replace(":= 8;", ":= 16;"))
    found = core.check(root)
    check(any("differs from the VHDL" in line for line in found), str(found))


@needs_ghdl
def test_check_finds_missing_and_stray_documents(tmp_path: Path) -> None:
    """A missing document and an unmatched one are both reported."""
    root = _repo(tmp_path)
    core.write(root, core.plan(root).documents)
    (root / "ipxact" / "demo_vendor.1.2.3.component.xml").unlink()
    stray = root / "ipxact" / "gone.1.2.3.component.xml"
    stray.write_text("<x/>")
    found = " ".join(core.differences(root, core.plan(root).documents))
    check_in("demo_vendor.1.2.3.component.xml: missing", found)
    check_in("gone.1.2.3.component.xml: stale", found)


@needs_ghdl
def test_unsupported_construct_needs_an_exception(tmp_path: Path) -> None:
    """An entity with no IP-XACT form is a problem until excepted."""
    root = _repo(
        tmp_path,
        manifest=MANIFEST.replace(
            "src/demo_vendor.vhd]", "src/demo_vendor.vhd, src/demo_int.vhd]"
        ),
    )
    (root / "src" / "demo_int.vhd").write_text(INTEGER_PORT)
    problems = core.plan(root).problems
    check(
        any(line.startswith("demo_int:") for line in problems),
        str(problems),
    )
    with (root / "paths.yaml").open("a") as handle:
        handle.write("ipxact:\n  exceptions:\n    demo_int: integer port\n")
    check_equal(core.plan(root).problems, [])


@needs_ghdl
def test_needless_exception_is_a_problem(tmp_path: Path) -> None:
    """An exception on an entity that translates is reported."""
    root = _repo(
        tmp_path, "ipxact:\n  exceptions:\n    demo_reg: not needed\n"
    )
    problems = core.plan(root).problems
    check(
        any("the entity translates" in line for line in problems),
        str(problems),
    )


@needs_ghdl
def test_command_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The three subcommands run from the command line."""
    root = _repo(tmp_path)

    def run(*words: str) -> None:
        """Run riscv-tools with the arguments."""
        monkeypatch.setattr(
            sys, "argv", ["riscv-tools", "--root", str(root), *words]
        )
        cli.main()

    with pytest.raises(SystemExit) as raised:
        run("ipxact", "generate", "--check")
    check_equal(raised.value.code, 1)
    run("ipxact", "generate")
    run("ipxact", "generate", "--check")
    run("ipxact", "check")
    run("ipxact", "extract")
    output = capsys.readouterr().out
    check_in("demo_reg (blocks, src/demo_reg.vhd)", output)
    check_not_in("Traceback", output)
