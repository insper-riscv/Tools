# `sdram_debug`

Reads and writes words of the SDRAM through its JTAG debug port: the equivalent of [`mem_edit`](mem_edit.md) for a memory outside the FPGA. The debug port is a second master of the SDRAM controller, behind a virtual JTAG instance (the word protocol is in [`docs/en/ram/sdram_debug.md`](https://github.com/insper-riscv/Memory/blob/main/docs/en/ram/sdram_debug.md) of the Memory), so the host reads and writes the memory with the core running, stopped or held.

A word address counts 32-bit words from the start of the chip, and not from the base of a region. The conversion from the byte address of the SoC to the word of the chip belongs to [`sdram_windows`](sdram_windows.md). [`ram_target`](ram_target.md) picks between this module and `mem_edit` for the RAM of a project, and [`flash_load`](flash_load.md) uses the operations of section 3 to write the FLASH.

## 1. Functions

| Function | Does |
| :--- | :--- |
| `read_words(link, word_address, word_count)` | reads contiguous words |
| `write_word(link, word_address, value, byte_enable)` | writes one word, the bytes selected by `byte_enable` |
| `fill(link, word_address, word_count, value)` | fills a range; the board executes it, so zeroing the 64 MB takes about two seconds |
| `load_words(link, word_address, words)` | writes contiguous words in one session, one per command |
| `capabilities(link)` | reads what the bitstream can do (section 3.1) |
| `set_hold(link, hold)` | holds or releases the core in reset |
| `crc32(link, word_address, word_count)` | CRC-32 of a range, computed by the board |
| `stream_write(link, word_address, words, burst)` | writes in bursts of `burst` words per shift; the rest, which does not fill a burst, goes word by word |
| `stream_read(link, word_address, word_count, burst)` | reads in bursts, with the same treatment of the rest |

## 2. Configuration

| Key | Meaning |
| :--- | :--- |
| `quartus.ram_backend` | `sdram_debug` makes the RAM the SDRAM behind this port; the default, `ismce`, is a memory instance of the FPGA |
| `quartus.sdram_debug_instance` | Index of the virtual JTAG instance of the debug port (3 in the generated top) |

## 3. Contract with the Memory

This section is the contract that the `sdram_dbg_master` and the `sdram_jtag_core` of the Memory fulfil so that the host writes the FLASH in bursts. The host only uses an operation that the capability word (section 3.1) announces, and a bitstream that does not announce it keeps working with the functions of section 1 that already existed.

The `DEBUG` register (instruction 1 of the virtual JTAG node) keeps today's 64-bit format.

| Direction | Fields |
| :--- | :--- |
| Input | `op` in bits 63 to 60, `be` in bits 59 to 56, word in bits 55 to 32, data in bits 31 to 0 |
| Output | status in bits 63 to 56, last word in bits 55 to 32, data read in bits 31 to 0 |

Bit 24 of the word address travels in bit 3 of `op`, as in the other operations. The status has `busy` (bit 0), `error` (bit 1), `SDRAM initialized` (bit 2) and `overrun` (bit 3). Operation 7, free today, becomes `CONTROL`, and the `be` field chooses the sub-command.

| `be` | Sub-command | Input | Effect and answer |
| :--- | :--- | :--- | :--- |
| 0 | `INFO` | none | The answer carries the capability word (section 3.1) |
| 1 | `HOLD` | bit 0 of the data | 1 holds the core in reset and 0 releases it; the answer returns the current level |
| 2 | `CRC_START` | first word in the word field and word count in the data | Clears the accumulator and walks the words through master B; stays `busy` until it ends |
| 3 | `CRC_READ` | none | The answer carries the CRC-32 of the last `CRC_START` |
| 4 | `POINTER` | first word in the word field | Loads the burst pointer of read and write; the read already fetches the first burst |

A sub-command that the bitstream does not implement answers with zero data and without the error bit, so `INFO` of an old bitstream reads zero and nothing is announced.

### 3.1. Capability word

| Bits | Field |
| :--- | :--- |
| 7 to 0 | Version of the contract, 1 in this document |
| 15 to 8 | Words per burst shift, from 1 to 128 (1024 to 4096 bits at most); 0 without burst |
| 16 | `HOLD` exists |
| 17 | `CRC_START` and `CRC_READ` exist |

### 3.2. The CRC-32

The accumulator starts at `0xFFFFFFFF`, processes the bytes of each word from the least to the most significant (little-endian, the memory order) with the reflected polynomial `0xEDB88320` and ends with the inversion of the 32 bits, the same result as `zlib.crc32` over the bytes of the range. The calculation runs in the controller clock and reads the words through master B, so it competes with the core and with the other cache through the round robin of the arbiter.

### 3.3. The burst

The burst uses two instructions of the virtual JTAG node, besides instruction 1.

| Instruction | Register | Effect |
| :--- | :--- | :--- |
| 2 | `STREAM_WRITE`, $32 N$ bits with $N$ the burst field | The shift carries $N$ words, word 0 in bits 31 to 0. On the update of the register the $N$ words go, with every byte enabled, to $N$ consecutive addresses from the pointer, which advances $N$ |
| 3 | `STREAM_READ`, $32 N$ bits | On the capture of the register, the $N$ words already fetched from the pointer are in the bits, word 0 in bits 31 to 0. On the update the pointer advances $N$ and the hardware fetches the next $N$ words |

Between two shifts the host goes back to instruction 1 and reads the status until `busy` falls. While the buffer of $N$ words is drained (write) or filled (read) the status stays `busy`, and a shift while `busy` would be lost, which the host never does. The pointer is loaded by the `POINTER` sub-command before the first burst, and the count of a call is always a multiple of $N$, the rest being handled by the word operations.

The reset button of the board restarts only the core. `HOLD` and the CRC accumulator only return to their initial value when the PLL lock is lost.

## 4. Prerequisites

- Quartus Prime Lite on `PATH` (`quartus_stp`) and a board with a USB-Blaster whose project has the debug port.

## 5. Tests

`tests/test_sdram_debug.py` runs the word functions against a stand-in of the script, and `tests/test_flash_load.py` runs `capabilities`, `set_hold`, `crc32` and the burst against a model of the board that follows the contract of section 3. On the board, the `de0-cv` platform of the Insper-RISC-V runs the real hardware suite through this module.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
