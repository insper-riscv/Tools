"""Assemble the boot memory of a platform and measure it.

The generated linker script already has an `ASSERT` that fails a boot
memory larger than the BOOT_MEMORY, but only when someone links it. The
measure here runs before the hardware: it assembles and links the
`boot_memory.S` of the platform with the toolchain, with the size
checks of the linker script switched off, so a boot memory that is too
big is measured instead of refused, and it says how many bytes each
source file (the base and one fragment per extension) put in the image.

The `boot_memory.S` is the sibling of the generated linker script
(`generate.boot_ld` of the platform), and the base ISA of the core
(`rv32i`, `rv32e`, `rv64i` or `rv64e`) is the `-march` of the build.
"""

import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, cast

from riscv_tools.boot_memory import boot_gcc_args
from riscv_tools.memory_map import core as map_core
from riscv_tools.memory_map.expressions import evaluate
from riscv_tools.memory_map.march import abi_of, platform_core

# Bytes de uma instrução da BOOT, que é só da base (sem a extensão C).
INSTRUCTION_BYTES = 4
BOOT_SOURCE = "boot_memory.S"
# Um ASSERT do linker script, com um nível de parênteses por dentro.
_ASSERT = re.compile(r"ASSERT\((?:[^()]|\([^()]*\))*\)\s*")
_LENGTH = re.compile(r"LENGTH\s*=\s*0x[0-9A-Fa-f]+")
# Maior comprimento que o linker script de medida dá à memória.
_WIDE = "LENGTH = 0x10000000"
_SECTION = re.compile(r"^\s*\d+\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s")
_LINE = re.compile(r"^(\S.*?):(\d+)(?: \(discriminator \d+\))?$")
_INSN = re.compile(r"^\s+[0-9a-f]+:\s")


@dataclass(frozen=True)
class BootSize:
    """What the assembled boot memory takes.

    Parameters
    ----------
    platform : str
        The platform file, from the project root, for the messages.
    used : int
        The bytes from the base of the BOOT_MEMORY to the end of the
        last section, the reserved gap of the wait point included.
    limit : int
        The size of the BOOT_MEMORY in bytes.
    base : str
        `rv32i`, `rv32e`, `rv64i` or `rv64e`, the `-march` of the build.
    by_file : dict of {str: int}
        The bytes of instructions that each source file put in the
        image, the heaviest first.
    """

    platform: str
    used: int
    limit: int
    base: str
    by_file: dict[str, int] = field(default_factory=dict[str, int])

    @property
    def fits(self) -> bool:
        """Say whether the boot memory fits the BOOT_MEMORY."""
        return self.used <= self.limit


def measure_script(text: str) -> str:
    """Turn a generated linker script into one that never refuses.

    Parameters
    ----------
    text : str
        The generated `boot_memory.ld`.

    Returns
    -------
    str
        The script without the `ASSERT` that compares the end of the
        image with the memory, and with a memory long enough for any
        boot memory. The `ASSERT` of the reset section stays.
    """
    out = _ASSERT.sub(
        lambda found: "" if "LENGTH(" in found.group(0) else found.group(0),
        text,
    )
    return _LENGTH.sub(_WIDE, out)


def _run(command: list[str]) -> str:
    """Run a tool and return what it prints.

    Parameters
    ----------
    command : list of str
        The program and its arguments.

    Returns
    -------
    str
        The standard output.

    Raises
    ------
    ValueError
        If the tool fails; the message has its error output.
    """
    try:
        done = subprocess.run(
            command, check=False, capture_output=True, text=True
        )
    except FileNotFoundError as error:
        raise ValueError(f"{command[0]} is not on the PATH") from error
    if done.returncode:
        raise ValueError(
            f"{PurePosixPath(command[0]).name} failed on the boot memory:\n"
            f"{done.stderr.strip()}"
        )
    return done.stdout


def _image_end(objdump: str, elf: Path) -> int:
    """Find the address where the last section of the image ends.

    Parameters
    ----------
    objdump : str
        The `objdump` of the toolchain.
    elf : Path
        The linked boot memory.

    Returns
    -------
    int
        The largest `address + size` of the sections that hold code.
    """
    end = 0
    for line in _run([objdump, "-h", str(elf)]).splitlines():
        found = _SECTION.match(line)
        if found and found.group(1).startswith(".text"):
            size, address = int(found.group(2), 16), int(found.group(3), 16)
            end = max(end, address + size)
    return end


def _bytes_by_file(objdump: str, elf: Path, root: Path) -> dict[str, int]:
    """Count the bytes of instructions that each source file put in.

    Parameters
    ----------
    objdump : str
        The `objdump` of the toolchain.
    elf : Path
        The boot memory linked with `-g`.
    root : Path
        The project root, which the names are made relative to.

    Returns
    -------
    dict of {str: int}
        The instruction bytes of each file, the heaviest first.
    """
    count: Counter[str] = Counter()
    current = ""
    listing = _run([objdump, "-d", "-l", "--no-show-raw-insn", str(elf)])
    for line in listing.splitlines():
        marker = _LINE.match(line)
        if marker:
            current = _relative(marker.group(1), root)
        elif current and _INSN.match(line):
            count[current] += INSTRUCTION_BYTES
    return dict(count.most_common())


def _relative(name: str, root: Path) -> str:
    """Write a source path relative to the project root.

    Parameters
    ----------
    name : str
        The path as the debug information holds it.
    root : Path
        The project root.

    Returns
    -------
    str
        The path from the root when the file is under it, with the
        `..` of the includes resolved, otherwise the name as it is.
    """
    path = Path(name).resolve()
    if path.is_relative_to(root.resolve()):
        return path.relative_to(root.resolve()).as_posix()
    return name


def _platform_paths(
    platform: dict[str, Any], platform_path: Path, root: Path
) -> tuple[Path, Path, int, int]:
    """Find the files and the BOOT_MEMORY of a platform.

    Parameters
    ----------
    platform : dict of {str: Any}
        The loaded platform.
    platform_path : Path
        The platform file.
    root : Path
        The project root.

    Returns
    -------
    tuple of (Path, Path, int, int)
        The generated linker script, the `boot_memory.S` beside it,
        and the base and size of the BOOT_MEMORY.

    Raises
    ------
    ValueError
        If the platform does not generate a boot linker script or its
        `boot_memory.S` is missing.
    """
    spec = map_core.platform_dict(platform, "generate").get("boot_ld")
    if not isinstance(spec, dict) or "path" not in spec:
        raise ValueError(
            f"{platform_path.name} has no generate.boot_ld, so there is "
            "no boot memory to measure"
        )
    script = root / str(cast(dict[str, Any], spec)["path"])
    source = script.parent / BOOT_SOURCE
    if not source.is_file():
        raise ValueError(f"{BOOT_SOURCE} is not beside {script}")
    first = map_core.platform_list(platform, "regions")[0]
    return script, source, evaluate(first["base"]), evaluate(first["size"])


def measure_boot_size(
    platform_path: Path,
    root: Path,
    build_dir: Path,
    gcc: str = "riscv32-unknown-elf-gcc",
    objdump: str = "riscv32-unknown-elf-objdump",
) -> BootSize:
    """Assemble the boot memory of a platform and measure it.

    Parameters
    ----------
    platform_path : Path
        The platform YAML.
    root : Path
        The project root, which the paths of the platform start from.
    build_dir : Path
        Where the measure build is written (created when missing).
    gcc : str, optional
        The compiler of the toolchain.
    objdump : str, optional
        The `objdump` of the toolchain.

    Returns
    -------
    BootSize
        The bytes the boot memory takes, the size of the BOOT_MEMORY
        and the bytes of each source file.

    Raises
    ------
    ValueError
        If the platform has nothing to measure or the toolchain fails.
    """
    platform = map_core.load_platform(platform_path)
    script, source, origin, limit = _platform_paths(
        platform, platform_path, root
    )
    core = platform_core(platform)
    base = f"rv{core['type']}{str(core['base']).lower()}"
    build_dir.mkdir(parents=True, exist_ok=True)
    wide = build_dir / "boot_memory_measure.ld"
    wide.write_text(measure_script(script.read_text()))
    elf = build_dir / "boot_memory_measure.elf"
    _run([gcc, *boot_gcc_args(base, abi_of(core), wide, source, elf, "-g")])
    return BootSize(
        platform=_relative(str(platform_path), root),
        used=_image_end(objdump, elf) - origin,
        limit=limit,
        base=base,
        by_file=_bytes_by_file(objdump, elf, root),
    )


def boot_size_message(size: BootSize) -> str:
    """Write the result of a measure for the terminal.

    Parameters
    ----------
    size : BootSize
        The measure.

    Returns
    -------
    str
        A headline (the size, or V-B3 with the overflow and what to
        do), then the bytes of each source file, the heaviest first.
    """
    if size.fits:
        head = (
            f"boot size OK: {size.used} of {size.limit} bytes "
            f"({size.base}) in {size.platform}"
        )
    else:
        head = (
            f"V-B3 the boot memory of {size.platform} assembles to "
            f"{size.used} bytes ({size.base}) and the BOOT_MEMORY has "
            f"{size.limit}, {size.used - size.limit} bytes over; drop an "
            "extension that the board does not use or grow "
            "memory.boot.size"
        )
    files = [
        f"  {taken:5d} bytes  {name}" for name, taken in size.by_file.items()
    ]
    return "\n".join([head, *files])
