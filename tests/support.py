"""Helpers shared by the test modules."""

from pathlib import Path


def write_rv32_header(root: Path, mailbox_addr: int) -> None:
    """Write include/rv32_test.h, with the mailbox at mailbox_addr."""
    include_dir = root / "include"
    include_dir.mkdir()
    (include_dir / "rv32_test.h").write_text(
        f"#define RV32_MAILBOX_ADDR ((volatile unsigned int *)"
        f"0x{mailbox_addr:08X})\n"
        "extern void rv32_wait_restart(void) __attribute__((noreturn));\n"
        "static inline void RV32_PASS(void) { *RV32_MAILBOX_ADDR = 1; "
        "rv32_wait_restart(); }\n"
        "static inline void RV32_FAIL(void) { *RV32_MAILBOX_ADDR = 2; "
        "rv32_wait_restart(); }\n"
    )
