# `sdram_windows`

Gives the host the window table of the SDRAM chip: where the FLASH and the RAM of a platform sit inside the chip, so that the `load-flash`, `dump-ram --region` and `load-ram` commands convert a byte address of the SoC into the word that the debug port of the SDRAM expects.

## 1. The window

A region in the SDRAM (`FLASH` or `RAM`) is a window of the chip.

| Field | Meaning |
| :--- | :--- |
| `base` | First byte address of the region in the SoC |
| `size` | Bytes of the region |
| `offset` | Byte of the chip where the region starts |

The byte address $A$ of the SoC, in $[\text{base}, \text{base} + \text{size})$, is in the word

$$ w = \frac{\text{offset} + (A - \text{base})}{4} $$

of the chip. A region without `offset` keeps the address of the SoC, and the byte of the chip is `base` modulo the smallest power of two that walks the region, the same as the generated top does.

## 2. Where the table comes from

| Source | Function | When |
| :--- | :--- | :--- |
| `platform.yaml` | `windows_from_platform`, `windows_from_platform_file` | The commands receive `--platform` |
| `memory.sdram_windows` of the `config.yaml` | `windows_from_config` | Without `--platform`; the section repeats the numbers of the platform |
| `memory.ram_base` and `memory.ram_words` | `windows_from_config` | Without the section; the RAM is a window at byte 0 of the chip |

```yaml
memory:
  sdram_windows:
    FLASH: {base: 0x1000, size: 0x1FFF000, offset: 0x1000}
    RAM:   {base: 0x40000000, size: 0x2000000, offset: 0x2000000}
```

## 3. Functions

| Function | Does |
| :--- | :--- |
| `Window.word_address(address)` | Converts the byte address of the SoC into the word of the chip, refusing what is not a word or leaves the region |
| `Window.contains(address, length)` | Tells whether a range of bytes fits the region |
| `window_named(windows, name)` | Finds `FLASH` or `RAM`, case-insensitive, or raises `WindowError` |

## 4. Tests

`tests/test_chip_split.py` covers the conversion of the three splits (32 and 32, 48 and 16, 16 and 48 MiB), the table of the configuration and the error of a region outside the SDRAM.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
