"""The image of a bank, built from the project config.

A platform whose boot memory chooses the bank by its header (the
`flash.banks` of its map) runs only a program that starts with the
header page. The config says which bank the programs are linked for:

```yaml
flash_image: {bank: A, version: 1}
```

and `flash.banks`, which comes from the platform map, lists the banks
with their `name`, `base` and `size`.
"""

from pathlib import Path
from typing import Any

from riscv_tools.flash_image.header import ImageError, pack


def image_for_config(
    cfg: dict[str, Any], build_dir: Path, name: str, bin_: Path
) -> tuple[Path, int | None]:
    """Pack the binary of a program into the image of its bank.

    Parameters
    ----------
    cfg : dict of {str: Any}
        The merged project config: `flash_image` and `flash.banks`.
    build_dir : Path
        Where the packed image is written.
    name : str
        The program name, for the file.
    bin_ : Path
        The flat binary the linker wrote, linked from the end of the
        header page of the bank.

    Returns
    -------
    tuple of (Path, int or None)
        The file to convert and the address its first byte has in the
        FLASH; the binary itself and None when the config has no
        `flash_image`.

    Raises
    ------
    ImageError
        If the config names a bank the map does not have, or the
        program does not fit in it.
    """
    spec = cfg.get("flash_image")
    if not spec:
        return bin_, None
    flash: dict[str, Any] = cfg.get("flash") or {}
    listed: list[dict[str, Any]] = flash.get("banks") or []
    banks: dict[str, dict[str, Any]] = {
        str(bank["name"]): bank for bank in listed
    }
    wanted = str(spec["bank"])
    if wanted not in banks:
        raise ImageError(
            f"flash_image.bank {wanted} is not in the platform map"
        )
    base = int(banks[wanted]["base"])
    size = int(banks[wanted]["size"])
    image = pack(bin_.read_bytes(), int(spec.get("version", 1)), size)
    packed = build_dir / f"{name}.image.bin"
    packed.write_bytes(image)
    return packed, base
