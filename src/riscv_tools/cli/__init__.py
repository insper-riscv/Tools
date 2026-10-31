"""Command-line entry point of ``riscv-tools``.

Usage: ``riscv-tools --config <config.yaml> <subcommand> ...``.

Every subcommand takes --config, pointing at the CONSUMING project's
own config.yaml (memory map, Quartus project paths, toolchain, etc.),
except `vhdl-sort`, `check-memory-map` and `check-paths`, which read
only files and need no project config at all.
"""

from riscv_tools.cli.board_cmd import (
    cmd_console,
    cmd_display,
    cmd_dump_ram,
    cmd_mailbox,
    cmd_program,
    cmd_write_rom,
    cmd_zero_ram,
)
from riscv_tools.cli.certify_cmd import cmd_certify, cmd_certify_board
from riscv_tools.cli.compile_cmd import cmd_compile
from riscv_tools.cli.golden_cmd import cmd_generate_golden, cmd_generate_header
from riscv_tools.cli.parser import main
from riscv_tools.cli.project import discover_tests
from riscv_tools.cli.spike_cmd import cmd_spike_run
from riscv_tools.cli.suite_cmd import cmd_run, cmd_sim, filter_manifest
from riscv_tools.cli.tools_cmd import (
    cmd_check_memory_map,
    cmd_check_paths,
    cmd_freq_sweep,
    cmd_profiles,
    cmd_timing_paths,
    cmd_vhdl_sort,
)

__all__ = [
    "cmd_certify",
    "cmd_certify_board",
    "cmd_check_memory_map",
    "cmd_check_paths",
    "cmd_compile",
    "cmd_console",
    "cmd_display",
    "cmd_dump_ram",
    "cmd_freq_sweep",
    "cmd_generate_golden",
    "cmd_generate_header",
    "cmd_mailbox",
    "cmd_profiles",
    "cmd_program",
    "cmd_run",
    "cmd_sim",
    "cmd_spike_run",
    "cmd_timing_paths",
    "cmd_vhdl_sort",
    "cmd_write_rom",
    "cmd_zero_ram",
    "discover_tests",
    "filter_manifest",
    "main",
]
