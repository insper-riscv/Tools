"""Commands that work on a project made by `new-project`."""

from riscv_tools.project.actions import (
    STOP_AFTER,
    TESTS_FOLDER,
    build_command,
    config_of_tests,
    flash_command,
)
from riscv_tools.project.doctor import (
    Check,
    board_idcode,
    check_cable,
    check_files,
    check_quartus,
    passed,
    render,
)
from riscv_tools.project.launcher import LAUNCHER_FILE, write_launcher
from riscv_tools.project.manifest import (
    PROJECT_FILE,
    Manifest,
    find_manifest,
    read_manifest,
    write_manifest,
)
from riscv_tools.project.tests_help import render_tests_help

__all__ = [
    "LAUNCHER_FILE",
    "PROJECT_FILE",
    "STOP_AFTER",
    "TESTS_FOLDER",
    "Check",
    "Manifest",
    "board_idcode",
    "build_command",
    "check_cable",
    "check_files",
    "check_quartus",
    "config_of_tests",
    "find_manifest",
    "flash_command",
    "passed",
    "read_manifest",
    "render",
    "render_tests_help",
    "write_launcher",
    "write_manifest",
]
