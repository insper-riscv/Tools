"""Prepare and launch Spike runs, shared by the golden generator and spike-run.

Spike and the GCC binutils come from the toolchain installed on the
workstation; this module only builds the command line, adds the symbols
Spike needs to an ELF copy, and checks the installed Spike is usable.
"""

import functools
import shutil
import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

# `nm`'s default output has exactly 3 whitespace-separated fields per
# symbol line: address, type, name.
_NM_LINE_FIELDS = 3
# Size in bytes of Spike's HTIF tohost register; fromhost follows it.
_HTIF_REGISTER_BYTES = 8
_SETUP_HINT = (
    "install Spike as described in insper-riscv/Infra's SPIKE_SETUP.md "
    "(it builds Spike with the debug module moved out of address 0)"
)


def symbol_address(nm_bin: str, elf_path: Path, symbol: str) -> int:
    """Resolve a symbol's address from an ELF's symbol table.

    Parameters
    ----------
    nm_bin : str
        `nm` binary name/path for the target toolchain (e.g.
        "riscv32-unknown-elf-nm").
    elf_path : Path
        Path to the ELF to inspect.
    symbol : str
        Symbol name to look up.

    Returns
    -------
    int
        The symbol's address.

    Raises
    ------
    RuntimeError
        symbol isn't present in elf_path's symbol table.
    """
    out = subprocess.run(
        [nm_bin, str(elf_path)], check=True, capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == _NM_LINE_FIELDS and parts[2] == symbol:
            return int(parts[0], 16)
    raise RuntimeError(f"symbol {symbol!r} not found in {elf_path}")


@functools.cache
def require_spike(spike_bin: str) -> str:
    """Return the path of a usable Spike, or raise with how to install one.

    "Usable" means the binary exists and places its debug module away
    from address 0: a stock build aborts at startup with `devices at
    [0, 1000) and [0, 10000) overlap` for any target whose ROM starts at
    address 0.

    Parameters
    ----------
    spike_bin : str
        The project's `emulator.spike_bin` (a name on `PATH`, or a path).

    Returns
    -------
    str
        Resolved path of the `spike` binary.

    Raises
    ------
    FileNotFoundError
        spike_bin isn't on `PATH` and isn't an existing file.
    RuntimeError
        The binary still places its debug module at address 0.
    """
    found = shutil.which(spike_bin)
    if found is None and Path(spike_bin).is_file():
        found = spike_bin
    if found is None:
        raise FileNotFoundError(f"{spike_bin!r} not found: {_SETUP_HINT}")

    probe = subprocess.run(
        [
            found,
            "--isa=rv32i",
            "-m0x0:0x10000",
            "--pc=0",
            "--disable-dtb",
            "/dev/null",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if "overlap" in probe.stdout + probe.stderr:
        raise RuntimeError(
            f"{found} places its debug module at address 0: {_SETUP_HINT}"
        )
    return found


def spike_command(  # noqa: PLR0913, PLR0917
    spike_bin: str,
    isa: str,
    mem_regions: list[tuple[int, int]],
    entry_pc: int,
    elf_path: Path,
    extra_args: tuple[str, ...] = (),
) -> list[str]:
    """Build a Spike command line that runs elf_path on the target's memory map.

    Spike's own default memory sits at 0x80000000 and its reset vector
    goes through a boot ROM at 0x1000, both of which collide with a
    target whose real memory starts near address 0. Passing every real
    region and starting at the ELF's entry point with no device tree
    sidesteps both.

    Parameters
    ----------
    spike_bin : str
        Resolved `spike` binary (see require_spike).
    isa : str
        `--isa=` value; must list extensions in Spike's canonical order.
    mem_regions : list of (int, int)
        (base, size) byte pairs, one per region of real memory.
    entry_pc : int
        Byte address execution starts at.
    elf_path : Path
        ELF to run.
    extra_args : tuple of str, optional
        Arguments placed before the ELF (e.g. `+signature=...`).

    Returns
    -------
    list of str
        The argument list for `subprocess.run`.
    """
    mem_flag = ",".join(f"{base:#x}:{size:#x}" for base, size in mem_regions)
    return [
        spike_bin,
        f"--isa={isa}",
        f"-m{mem_flag}",
        "--disable-dtb",
        f"--pc={entry_pc:#x}",
        *extra_args,
        str(elf_path),
    ]


@contextmanager
def prepared_elf(
    objcopy_bin: str,
    nm_bin: str,
    elf_path: Path,
    tohost_symbol: str,
    extra_symbols: dict[str, int] | None = None,
) -> Generator[Path]:
    """Yield a temporary copy of elf_path that has the symbols Spike needs.

    Spike's HTIF looks up `tohost` and `fromhost` by those exact names;
    without both it prints a warning and never exits on completion. The
    copy gets `tohost` as an alias when the project uses another name,
    `fromhost` right after `tohost` when the link script doesn't define
    it, and any extra symbols requested (e.g. `begin_signature`).

    Parameters
    ----------
    objcopy_bin : str
        `objcopy` binary for the target toolchain.
    nm_bin : str
        `nm` binary for the target toolchain.
    elf_path : Path
        Original ELF, left untouched.
    tohost_symbol : str
        Name of the symbol the program writes on completion.
    extra_symbols : dict of {str: int}, optional
        Additional absolute symbols to define, name to address.

    Yields
    ------
    Path
        Path of the temporary ELF; removed when the context exits.

    Raises
    ------
    RuntimeError
        tohost_symbol isn't in the ELF.
    subprocess.CalledProcessError
        `objcopy` failed.
    """
    tohost_addr = symbol_address(nm_bin, elf_path, tohost_symbol)
    symbols = dict(extra_symbols or {})
    if tohost_symbol != "tohost":
        symbols["tohost"] = tohost_addr
    try:
        symbol_address(nm_bin, elf_path, "fromhost")
    except RuntimeError:
        symbols["fromhost"] = tohost_addr + _HTIF_REGISTER_BYTES

    with tempfile.TemporaryDirectory(prefix="riscv-tools-spike-") as tmp:
        out = Path(tmp) / elf_path.name
        cmd = [objcopy_bin]
        for name, addr in symbols.items():
            cmd += ["--add-symbol", f"{name}={addr:#x},global"]
        subprocess.run([*cmd, str(elf_path), str(out)], check=True)
        yield out
