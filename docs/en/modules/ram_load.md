# `ram_load`

Loads one or more files into the SDRAM through the JTAG debug port ([`sdram_debug`](sdram_debug.md)), reads each back to verify it and only then writes the magic to the `launch` word, which tells the program on the board that the image is complete. It is the `load-ram` subcommand.

## 1. Flow

| Step | Operation |
| :--- | :--- |
| 1 | The `launch` word is cleared, so an old magic cannot start a half-written image |
| 2 | Each file is written by `sdram_debug.load_words` in a single script session |
| 3 | The file is read back in blocks of 65,536 words and compared; the first difference aborts the load, with the magic still unwritten |
| 4 | The magic is written to `launch`, always last |

The whole request is validated before step 1: word-aligned addresses, inside the SDRAM, no overlap and nothing covering `launch`. An invalid request writes nothing. The last word of a file whose size is not a multiple of 4 is padded with zeros.

## 2. Configuration

| Key | Meaning |
| :--- | :--- |
| `memory.ram_base` | Byte address of the SDRAM base, the default address of the binary |
| `memory.ram_words` | SDRAM size in words, which bounds the segments |
| `memory.launch_addr` | Address of the `launch` word, which the platform map reserves in `reserved.launch` |

## 3. Options

| Option | Meaning |
| :--- | :--- |
| `binary` | File loaded at `--address` |
| `--address` | Byte address of the binary; the SDRAM base when omitted |
| `--wad` and `--wad-address` | Second file and its address, above the binary; given together |
| `--launch-address` | Address of the `launch` word, in place of `memory.launch_addr` |
| `--magic` | Value written to `launch`, `0x4D4F4F44` by default |
| `--no-launch` | Load without writing the magic |
| `--no-verify` | Skip the read-back |

## 4. Requirements

- Quartus Prime Lite on the `PATH` (`quartus_stp`) and a board with a USB-Blaster whose project has the SDRAM debug port and the program that polls `launch` (the `doom` platform of Insper-RISC-V).

## 5. Tests

`tests/test_ram_load.py` runs the module against an in-memory SDRAM in place of the script: write order (magic last), a read-back difference, invalid requests, a 4,196,020-byte WAD and the subcommand.

## 6. Usage

```bash
uv run riscv-tools --config src/cyclone-v/doom/config.yaml load-ram doom.bin \
    --wad doom1.wad --wad-address 0x40100000
```

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
