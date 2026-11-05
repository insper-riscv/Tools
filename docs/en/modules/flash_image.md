# `flash_image`

Packs a program into the image of a FLASH bank, checks an image and sends it, over the JTAG UART, to the program that updates the FLASH. The module knows only the image format; the update routine of the system erases and writes the FLASH, and the map of the banks comes from the `platform.yaml` (see [`memory_map`](memory_map.md)).

## 1. Image format

A bank starts with a 256-byte header page, and the program (the payload) follows it. The fields are little-endian 32-bit words, and the rest of the page stays erased (`0xFF`). The update routine writes the payload first and the header page last, so a bank without a valid header is a bank whose update did not finish.

| Offset | Field | Content |
| :--- | :--- | :--- |
| 0 | magic | `0x52564946` |
| 4 | size | bytes of the payload, a multiple of 4 |
| 8 | crc | CRC-32 (IEEE 802.3, as zlib) of the payload |
| 12 | version | version of the image; the larger is the newer |
| 16 | header crc | CRC-32 of the first 16 bytes |

The payload is the `.bin` the linker produced for the bank, padded with `0xFF` to a multiple of 4 bytes. The program of a bank is linked from `base + 256` (the `BANK_<name>_PAYLOAD` symbols of the map).

## 2. Functions

| Function | Does |
| :--- | :--- |
| `pack(payload, version, bank_size)` | returns the header page followed by the payload; refuses an empty payload, a version outside $[0, 2^{32}-2]$ and an image larger than the bank |
| `parse_header(image)` | reads and validates the header (magic, header CRC, size); an erased bank is refused by its magic |
| `verify(image)` | checks the header, the length and the CRC of the payload |
| `send_image(link, image, on_bytes)` | gives the bytes of the image, in order and in 16 KiB blocks, to the JTAG UART; the program reads the header and then as many bytes as it says |

## 3. Command

```bash
riscv-tools --root <project> flash-image pack program.bin --output image.bin --version 3 --platform src/cyclone-v/de0-cv/platform.yaml --bank B
riscv-tools flash-image verify image.bin
riscv-tools --config <config.yaml> flash-image send image.bin
```

`pack` with `--platform` and `--bank` checks that the image fits the bank. `send` requires `--config` and checks the image before sending it; what the program prints during the transfer goes to standard output. `pack` and `verify` do not need `--config`.

## 4. Prerequisites

- `send`: Quartus Prime Lite on the `PATH` (`quartus_stp`) and a board with a USB-Blaster whose project has the JTAG UART.

## 5. Tests

`tests/test_flash_image.py` covers the format, the damage the check must catch and the transfer against a stand-in reader.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
