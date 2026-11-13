"""Tests for new_project and the `new-project` subcommand."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from support import (
    check,
    check_equal,
    check_false,
    check_in,
    check_not_in,
    profile_matrix,
)

from riscv_tools import cli
from riscv_tools.new_project import (
    ProjectSpec,
    create_platform,
    parse_cache,
    parse_size,
    validate,
)
from riscv_tools.new_project.layout import flash_banks, reserved_bases
from riscv_tools.new_project.platform_text import rewrite_platform
from riscv_tools.new_project.register import (
    register_paths,
    register_sources,
)
from riscv_tools.new_project.template import (
    Template,
    find_template,
    rename_text,
)

PLATFORM = """\
# The fpga-demo platform.
platform: fpga-demo
board: auto
boards: [demo-board]
top: Insper-RISC-V/fpga_demo_board
core:
  type: 32
  base: I
  extensions: []
memory:
  boot:
    base: 0x00000000
    size: 4K
  instructions:
    - type: emulated
      base: 0x00001000
      size: 252K
      on_bus: true
      sector_bytes: 4096
      cache:
        size_bits: 32768
  data:
    - type: sdram   # the SDRAM
      base: 0x40000000
      size: 64M
      on_bus: true
      cache:
        size_bits: 32768
reserved:
  stdout:
    base: 0x43FFFBE0
    size: 1K+8
  tohost:
    base: 0x43FFFFE8
    size: 8
  fromhost:
    base: 0x43FFFFF0
    size: 8
flash:
  region: FLASH
  banks:
    - {name: A, base: 0x00001000, size: 124K}
    - {name: B, base: 0x00020000, size: 128K}
peripherals:
  UART:
    base: 0xC0000000
    size: 1K
"""
CONFIG = """\
toolchain:
  specs: src/fam/fpga-demo/runtime/rv32im-fpga.specs
sim:
  toplevel: old_sim_test
quartus:
  project_dir: build/fpga-demo-demo-board
  project_name: fpga_demo_demo_board
"""
SIM_TOP = "entity old_sim_test is\nend entity;\n-- fpga_demo_map_pkg\n"
PATHS = """\
tree:
  other: 1
  - {name: platforms, paths: [src/fam/fpga-demo/platform.yaml, src/x/y.yaml]}
components:
  fpga_demo_map:
    requires: [Common-Components/utils]
    sources:
      - src/fam/fpga-demo/config_pkg.vhd
  fpga_demo_board:
    requires: [sdram_board, fpga_demo_map]
    sources: []
  fpga_demo_sim_top:
    requires: [fpga_demo_map, Core/core]
    sources:
      - src/fam/fpga-demo/fpga-demo_sim_top.vhd
  other:
    sources: []
"""
SCRIPT = (
    "YAMLS = (\n"
    '    Saida("src/fam/fpga-demo/config.yaml", ("fpga_demo_sim_top",)),\n'
    ")\n"
)
SPEC = ProjectSpec(
    name="demo-64k",
    board="demo-board",
    profile="rv32im",
    rom_bytes=64 * 1024,
    ram_bytes=64 * 1024,
    icache_bits=0,
    dcache_bits=16384,
)


def _repo(root: Path, *, script: str = SCRIPT) -> Path:
    """Write a small Insper-RISC-V checkout with one platform."""
    folder = root / "src/fam/fpga-demo"
    (folder / "runtime").mkdir(parents=True)
    (folder / "platform.yaml").write_text(PLATFORM)
    (folder / "config.yaml").write_text(CONFIG)
    (folder / "fpga_demo_map_pkg.vhd").write_text("-- map\n")
    (folder / "fpga-demo_sim_top.vhd").write_text(SIM_TOP)
    (folder / "runtime/memory_map.h").write_text("/* fpga-demo */\n")
    (root / "Core/profiles").mkdir(parents=True)
    (root / "Core/profiles/matrix.yaml").write_text(
        yaml.safe_dump(profile_matrix("rv32i"))
    )
    (root / "boards/demo-board").mkdir(parents=True)
    (root / "boards/demo-board/board.yaml").write_text("board: demo-board\n")
    (root / "paths.yaml").write_text(PATHS)
    (root / "scripts").mkdir()
    (root / "scripts/generate_sources.py").write_text(script)
    return root


def _template() -> Template:
    """Describe the platform of the small checkout."""
    return Template(
        Path("src/fam/fpga-demo"),
        "demo-board",
        "Insper-RISC-V/fpga_demo_board",
    )


def test_sizes_are_read_in_bytes() -> None:
    """`64K`, `1M` and plain numbers become bytes."""
    check_equal(parse_size("64K"), 65536)
    check_equal(parse_size("1m"), 1 << 20)
    check_equal(parse_size("4096"), 4096)


@pytest.mark.parametrize("text", ["", "0", "K", "1G", "-4K", "6.5K"])
def test_a_malformed_size_is_refused(text: str) -> None:
    """Anything but digits and an optional K or M is an error."""
    with pytest.raises(ValueError, match="size"):
        parse_size(text)


def test_caches_are_a_size_or_off() -> None:
    """`off` and `0` turn a cache off; a number is its size in bits."""
    check_equal(parse_cache("off"), 0)
    check_equal(parse_cache("0"), 0)
    check_equal(parse_cache("32768"), 32768)
    with pytest.raises(ValueError, match="cache"):
        parse_cache("big")


def test_the_choices_are_checked_against_the_catalog() -> None:
    """A bad name, board, profile or size is refused."""
    boards, profiles = ["demo-board"], ["rv32im"]
    validate(SPEC, boards, profiles)
    bad: list[tuple[dict[str, Any], str]] = [
        ({"name": "Demo"}, "lower case"),
        ({"board": "other"}, "demo-board"),
        ({"profile": "rv32x"}, "unknown profile"),
        ({"rom_bytes": 12288}, "multiple of 8192"),
        ({"ram_bytes": 1000}, "multiple of 4096"),
    ]
    for change, message in bad:
        spec = ProjectSpec(**{**SPEC.__dict__, **change})
        with pytest.raises(ValueError, match=message):
            validate(spec, boards, profiles)


def test_the_host_words_sit_at_the_top_of_the_ram() -> None:
    """`stdout`, `tohost` and `fromhost` follow the end of the RAM."""
    check_equal(
        reserved_bases(0x40000000, 64 * 1024),
        {
            "stdout": 0x4000FBE0,
            "tohost": 0x4000FFE8,
            "fromhost": 0x4000FFF0,
        },
    )


def test_the_flash_splits_into_two_banks_of_whole_sectors() -> None:
    """Two equal banks when sectors divide, else A takes the extra."""
    even = flash_banks(0x1000, 64 * 1024, 4096)
    check_equal(
        [(b.name, b.base, b.size) for b in even][1], ("B", 0x9000, 32768)
    )
    odd = flash_banks(0x1000, 60 * 1024, 4096)
    check_equal([b.size for b in odd], [32768, 28672])


def test_the_platform_file_follows_the_choices() -> None:
    """Sizes, words, banks, caches, profile and names are rewritten."""
    top = "Insper-RISC-V/demo_64k_board"
    text = rewrite_platform(PLATFORM, SPEC, "fpga-demo", top)
    data = yaml.safe_load(text)
    check_equal(data["platform"], "demo-64k")
    check_equal(data["top"], top)
    check_equal(data["core"], {"type": 32, "base": "I", "extensions": ["M"]})
    memory = data["memory"]
    sizes = (memory["instructions"][0]["size"], memory["data"][0]["size"])
    check_equal(sizes, ("64K", "64K"))
    check_equal(data["reserved"]["tohost"]["base"], 0x4000FFE8)
    banks = {b["name"]: (b["base"], b["size"]) for b in data["flash"]["banks"]}
    check_equal(banks, {"A": (0x1000, "32K"), "B": (0x9000, "32K")})
    check_not_in("cache", memory["instructions"][0])
    check_equal(memory["data"][0]["cache"], {"size_bits": 16384})
    check_equal(memory["data"][0]["on_bus"], True)
    check_in("# The fpga-demo platform.", text)
    check_in("# the SDRAM", text)


def test_a_choice_left_out_keeps_the_template_value() -> None:
    """A field at None changes nothing in the template's file."""
    spec = ProjectSpec(name="demo-keep", board="demo-board")
    data = yaml.safe_load(rewrite_platform(PLATFORM, spec, "fpga-demo", "t"))
    check_equal(data["core"], {"type": 32, "base": "I", "extensions": []})
    check_equal(data["memory"]["data"][0]["size"], "64M")
    inst = data["memory"]["instructions"][0]
    check_equal(inst["cache"]["size_bits"], 32768)


def test_a_template_without_the_expected_line_is_refused() -> None:
    """A missing size line is an error, not a silent skip."""
    text = PLATFORM.replace("      size: 252K\n", "")
    with pytest.raises(ValueError, match="no `size:` line"):
        rewrite_platform(text, SPEC, "fpga-demo", "t")


def test_names_are_renamed_in_text() -> None:
    """Folder, VHDL names, file names and project names change."""
    text = (
        "src/fam/fpga-demo/runtime/x.S fpga_demo_map_pkg fpga-demo_sim_top\n"
        "build/fpga-demo-demo-board fpga_demo_demo_board demo-board\n"
    )
    out = rename_text(text, "fpga-demo", "new-1", "demo-board")
    check_in("src/fam/new-1/runtime/x.S", out)
    check_in("new_1_map_pkg", out)
    check_in("new-1_sim_top", out)
    check_in("build/new-1-demo-board", out)
    check_in("new_1_demo_board", out)
    check_equal(rename_text(out, "fpga-demo", "new-1", "demo-board"), out)


def test_the_template_is_the_platform_of_the_board(tmp_path: Path) -> None:
    """One platform lists the board; none or two is an error."""
    repo = _repo(tmp_path)
    check_equal(find_template(repo, "demo-board").name, "fpga-demo")
    with pytest.raises(ValueError, match="exactly one"):
        find_template(repo, "other-board")


def test_paths_gain_the_platform_and_its_three_components() -> None:
    """The list and copies of the map, board and simulation top."""
    text = register_paths(PATHS, _template(), "new-1")
    data = yaml.safe_load(text.replace("  - {name", "  other2: {name", 1))
    check_in("src/fam/new-1/platform.yaml", text)
    components = data["components"]
    for name in ("new_1_map", "new_1_board", "new_1_sim_top"):
        check_in(name, components)
    check_equal(
        components["new_1_board"]["requires"], ["sdram_board", "new_1_map"]
    )
    check_equal(
        components["new_1_sim_top"]["sources"],
        ["src/fam/new-1/new-1_sim_top.vhd"],
    )
    check_in("fpga_demo_sim_top", components)


def test_the_script_gains_a_line_or_reports_none() -> None:
    """A copy of the template's line, or None when it is absent."""
    out = register_sources(SCRIPT, _template(), "new-1")
    check(out is not None)
    check_in(
        'Saida("src/fam/new-1/config.yaml", ("new_1_sim_top",))', out or ""
    )
    check(register_sources("YAMLS = ()\n", _template(), "new-1") is None)


def test_the_platform_is_created_and_registered(tmp_path: Path) -> None:
    """Files, names, the entity, paths.yaml and the script change."""
    repo = _repo(tmp_path)
    created = create_platform(repo, SPEC)
    folder = repo / created.folder
    check_equal(created.folder, Path("src/fam/demo-64k"))
    check(created.script_edited)
    check((folder / "demo_64k_map_pkg.vhd").is_file())
    check((folder / "demo-64k_sim_top.vhd").is_file())
    config = yaml.safe_load((folder / "config.yaml").read_text())
    check_equal(config["sim"]["toplevel"], "demo_64k_sim_test")
    check_equal(config["quartus"]["project_name"], "demo_64k_demo_board")
    check_in(
        "entity demo_64k_sim_test",
        (folder / "demo-64k_sim_top.vhd").read_text(),
    )
    check_in("demo_64k_board", (repo / "paths.yaml").read_text())
    check_in("demo-64k", (repo / "scripts/generate_sources.py").read_text())
    check_equal(
        (repo / "src/fam/fpga-demo/platform.yaml").read_text(), PLATFORM
    )


def test_nothing_is_copied_when_the_repository_cannot_be_edited(
    tmp_path: Path,
) -> None:
    """A paths.yaml without the platform list leaves no new folder."""
    repo = _repo(tmp_path)
    (repo / "paths.yaml").write_text("tree: {}\n")
    with pytest.raises(ValueError, match="platforms"):
        create_platform(repo, SPEC)
    check_false((repo / "src/fam/demo-64k").exists())


def test_an_existing_platform_is_not_overwritten(tmp_path: Path) -> None:
    """Creating the same name twice fails the second time."""
    repo = _repo(tmp_path)
    create_platform(repo, SPEC)
    with pytest.raises(FileExistsError):
        create_platform(repo, SPEC)


def _run(monkeypatch: pytest.MonkeyPatch, repo: Path, *extra: str) -> None:
    """Run `riscv-tools new-project` on a checkout, not generating."""
    argv = ["riscv-tools", "new-project", "demo-64k"]
    argv += ["--board", "demo-board", "--profile", "rv32im"]
    argv += ["--rom", "64K", "--ram", "64K", "--icache", "off"]
    argv += ["--repo", str(repo), "--no-generate", *extra]
    monkeypatch.setattr("sys.argv", argv)
    cli.main()


def test_the_command_prints_the_help_and_runs_without_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The help names the files and the peripherals, in Portuguese."""
    repo = _repo(tmp_path / "Insper-RISC-V")
    _run(monkeypatch, repo)
    out = capsys.readouterr().out
    check_in("Projeto 'demo-64k' pronto", out)
    check_in("src/fam/demo-64k/platform.yaml", out)
    check_in("FLASH 64K, RAM 64K, icache off", out)
    check_in("UART", out)
    check_in("Como mudar o projeto", out)


def test_the_help_can_be_printed_in_english(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--lang en` prints the English help."""
    repo = _repo(tmp_path / "Insper-RISC-V")
    _run(monkeypatch, repo, "--lang", "en")
    out = capsys.readouterr().out
    check_in("How to change the project", out)
    check_not_in("Como mudar", out)


def test_the_command_refuses_an_unknown_board(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unknown board exits with status 1 and lists the known ones."""
    repo = _repo(tmp_path / "Insper-RISC-V")
    argv = ["riscv-tools", "new-project", "demo-64k", "--board", "nope"]
    argv += ["--repo", str(repo), "--no-generate"]
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as stop:
        cli.main()
    check_equal(stop.value.code, 1)
    check_in("demo-board", capsys.readouterr().err)


def test_the_command_writes_the_manifest_and_the_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The project folder gets `project.yaml` and the `rt` script."""
    repo = _repo(tmp_path / "Insper-RISC-V")
    _run(monkeypatch, repo)
    project = tmp_path
    data = yaml.safe_load((project / "project.yaml").read_text())
    check_equal(data["board"], "demo-board")
    check_equal(data["platform"], "src/fam/demo-64k")
    check_equal(data["repo"], "Insper-RISC-V")
    check((project / "rt").is_file())


def test_a_profile_without_zifencei_is_refused_when_the_boot_needs_it(
    tmp_path: Path,
) -> None:
    """A boot memory with `fence.i` needs a core with Zifencei."""
    repo = _repo(tmp_path)
    boot = repo / "src/fam/fpga-demo/runtime/boot_memory.S"
    boot.write_text("    .word 0x0000100F  // fence.i\n")
    with pytest.raises(ValueError, match=r"Zifencei.*rv32im_zifencei"):
        create_platform(repo, SPEC)
    check_false((repo / "src/fam/demo-64k").exists())


def test_a_boot_without_fence_i_accepts_any_profile(tmp_path: Path) -> None:
    """Without `fence.i` in the boot memory the profile is free."""
    repo = _repo(tmp_path)
    boot = repo / "src/fam/fpga-demo/runtime/boot_memory.S"
    boot.write_text("_reset:\n    j _reset\n")
    created = create_platform(repo, SPEC)
    check_equal(created.folder, Path("src/fam/demo-64k"))
