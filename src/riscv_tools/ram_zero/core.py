import tempfile
from pathlib import Path

from riscv_tools import mem_edit
from riscv_tools.jtag import JtagLink


def _blank_mif(depth: int) -> Path:
    """A full-depth all-zero .mif — mem_edit.write_full always
    overwrites the whole instance, so "zero it" just means "write
    this" rather than needing a dedicated zeroing primitive on the
    Quartus side."""
    lines = [
        "WIDTH=32;", f"DEPTH={depth};", "",
        "ADDRESS_RADIX=HEX;", "DATA_RADIX=HEX;", "",
        "CONTENT BEGIN",
        f"    [0000..{depth - 1:04X}] : 00000000;",
        "END;",
    ]
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".mif", delete=False)
    f.write("\n".join(lines) + "\n")
    f.close()
    return Path(f.name)


def zero_ram(link: JtagLink, ram_mem_instance: int, ram_words: int) -> None:
    """Clears every word of RAM over JTAG, without reprogramming the
    FPGA. Useful between test runs when a program's own crt0 restart
    path (mailbox/go_flag self-clear) isn't enough — e.g. re-running
    an integration test that dumps and compares the whole RAM, where
    leftover words from a previous test would corrupt the comparison."""
    blank = _blank_mif(ram_words)
    try:
        mem_edit.write_full(link, ram_mem_instance, blank)
    finally:
        blank.unlink(missing_ok=True)
