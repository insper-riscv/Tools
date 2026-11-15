# `flash_load`

Writes the FLASH that sits in the SDRAM through the debug port, with the core held, and checks the write with the CRC-32 that the board computes. It is what `riscv-tools load-flash`, `flash-image send --via debug` and the `sdram_debug` method of [`rom_writer`](rom_writer.md) use.

## 1. Flow

1. The bitstream has to announce `HOLD` and CRC ([`sdram_debug`](sdram_debug.md), section 3.1). Without both, the write is refused before any store, because the core and the JTAG would write the FLASH at the same time and the caches would keep old lines.
2. The core is held in reset. The reset clears the valid lines of the instruction cache, so the core that leaves reset fetches from the SDRAM.
3. The content is written in bursts. The first bytes of a bank, the 256-byte header, go last, and an interrupted write leaves a bank that the BOOT does not validate.
4. The CRC-32 of the range, computed by the board, is compared with the one of the content.
5. The core is released, also when the check fails, and the BOOT picks the intact bank of the highest version.

The reset button of the board restarts only the core, so the content of the FLASH survives it. A reconfiguration of the FPGA erases the SDRAM, and the FLASH is written again after it.

## 2. Request

| Check | Error |
| :--- | :--- |
| Empty content | `the image is empty` |
| Address or header that is not a word | `the address and the header must be words` |
| Range outside the `FLASH` region | `is outside the FLASH` |
| Bitstream without `HOLD` and CRC | `no hold and CRC` |
| CRC of the board different from the content | `CRC-32 of the board` |

## 3. ELF

`load_segments` reads the `PT_LOAD` segments of a 32-bit little-endian ELF, and `flat_binary` joins them into a contiguous binary with zeros in the gaps. With `--bank`, `load-flash` packs the binary with the header of the bank, and the program has to start 256 bytes after the base of the bank. Without `--bank`, a one-segment ELF is written at its load address.

## 4. Command

```bash
uv run riscv-tools --config config.yaml load-flash --platform src/platform.yaml --elf app.elf --bank A --version 3
uv run riscv-tools --config config.yaml load-flash --image img.bin --bank A
uv run riscv-tools --config config.yaml load-flash --image raw.bin --address 0x1000
```

## 5. Tests

`tests/test_flash_load.py` runs the flow against a model of the board: the burst, `HOLD`, the order of the header, the CRC, the refused requests and the ELF.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
