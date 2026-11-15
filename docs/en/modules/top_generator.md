# `top_generator`

Generates the thin board top, which only wires the PLL, the SoC, one backend per region and the pin ring.

## 1. Purpose

The generated top has no logic besides the reset. It wires, in this order, the board ports, the PLL (a Verilog module, instantiated by component), the `soc` entity instance, the boot memory, the I/O roles, the console and one backend per external region, with the tri-state pin ring.

## 2. Content

| Part | Origin |
| :--- | :--- |
| Generics `HPM_COUNTERS` and `HPM_WIDTH` | Present when the profile has Zihpm, passed to the SoC |
| Reset | User reset normalized to active `'1'`, SoC reset released two `core` cycles after the PLL locks |
| SoC generics | Constants of the map package (`generate.vhdl.package`), including `periph_count`, `periph_bases` and `periph_masks` (the `PERIPH_*` tables), `strict_periph` and one `<peripheral>_index` (`clint_index`, `plic_index`, `uart_jtag_index`, `flash_ctrl_index` and the like) for each peripheral the platform lists, taken from its `<NAME>_INDEX`, so the top fixes no peripheral number; with timers (`kind: timer`), `timer_indices => TIMER_INDICES` and `timer_irq_ids => TIMER_IRQ_IDS`, one SoC instance per row; without a PLIC in the platform, the PLIC and CLINT generics take the SoC defaults, so the top never reads constants the package lacks; ISA extension generics are not passed, the SoC reads them from the platform `config_pkg` |
| Polarity | The SoC generics `switches_active_low`, `keys_active_low` and `display_active_low`; switches and keys are `inout` ports wired straight to the GPIO pins |
| `emulado` FLASH backend | `flash_chip` (latencies from `memory.rom.latency`), the dual-port `flash`, `flash_loader` and `flash_jtag_shell`; the loader holds the SoC in reset while it writes |
| Program update | With the `FLASH_CTRL` peripheral the SoC carries the controller (`has_flash_ctrl`) and the FLASH backend adds the `flash_cmd_port` on port B of the storage, which the loader takes while the core is stopped, and returns the rewritten region to the SoC so it drops the cache lines |
| Critical path cuts | The top turns on `registered_irqs`, `fast_icache_select` (with the fetch clock defined) and the page at the top of the RAM outside the data cache (`RAM_LAST_PAGE`), the same cuts as the hand-written top |
| `emulado` RAM backend | `onchip_ram_port` over the `ram` block, with the requested latency |
| `dispositivo/sdram` backend | Two bridges (data and instruction), `sdram_arbiter`, `sdram_dbg_master`, `sdram_jtag_shell`, `sdram_ctrl` and one `tristate_buffer_1bit` per data bit in a `generate`; the 16 or 32-bit width and the row, column and bank bits come from the chip and from `memories.sdram.chips` |
| `dispositivo/nor` backend | 8-bit `nor_flash_ctrl` with page read and the program update commands, and the FLASH pin ring |
| `dispositivo/sram` backend | `sram_ctrl` on the data port of the SoC, with the `ADDR` (20 bits), `CE#`, `OE#`, `WE#`, `LB#` and `UB#` pins wired directly, one `tristate_buffer_1bit` for each bit of the 16-bit `DQ`, the size of the chip package and the timings of `chip_timing_pkg`; the instruction port of the RAM gets no answer, as in the emulated RAM |

## 3. What the top does not wire

A backend without an entity (`flash-interna` and `serial`) generates no instance: the top warns and leaves the region idle. The SoC does not export the LED role: the LED pins stay at the off level, except the first one, which lights with the failure flag the host writes to the display (Virtual JTAG node of index 2). The text of each backend lives in `templates/`, with the real names and ports of the Memory entities.

### 3.1. Video

When the platform asks for video, the `TopSpec` carries the `VideoPlan` and `video_generics` writes the generics of timing, channel width and framebuffer ([board_video](board_video.md)). The top wires only `channel_bits` to the `video` peripheral (section 3.2), and the generic map of the SoC does not receive the generics of the plan.

### 3.2. External peripherals

Each entry of `peripherals` with an external `kind` (section 9.6 of [memory_map](memory_map.md)) becomes an instance of the `Peripherals` entity, labelled `u_<name>`, wired to the pins of the board role and to an external bus of the SoC. Without an external peripheral the top gets nothing, and a peripheral the board omits (`need: optional`) has its read data and its interrupt tied to zero.

The contract with the SoC is the following.

| Item | Content |
| :--- | :--- |
| Generics | `ext_indices => EXT_INDICES`, `ext_irq_ids => EXT_IRQ_IDS` (the tables of the map package) and `ext_addr_width`, the largest word address width among the entities |
| Output ports | `o_ext_addr`, `o_ext_wdata`, `o_ext_byteena`, `o_ext_we` and `o_ext_re`, the latter and the one before it with one bit per peripheral |
| Input ports | `i_ext_rdata` (32 bits per peripheral) and `i_ext_irq` (one bit per peripheral) |
| Position | `<NAME>_EXT_POS`, from the map package, picks the slice of each peripheral |

The instance wires `i_clk` to the core clock and `i_rst` to the SoC reset, and the frequency generics receive the core clock in hertz. The fields of the kind (for example `phy_addr`, `cs_count`, `three_wire`, `has_flow_control`, `sample_rate`) become generics with the same name as the field, and only the fields written in the platform enter the `generic map`. The types of the fields and the literal of each one are in section 9.7 of [memory_map](memory_map.md).

| Entity | Pins |
| :--- | :--- |
| `ps2_keyboard`, `ps2_mouse_top` | `clk` and `dat` straight to the `inout` ports |
| `sd_spi` | MOSI on `cmd`, MISO on `dat(0)`, CS on `dat(3)`, and the other bits of `dat` at `'Z'` |
| `sd_native` | `cmd` and each bit of `dat` go out through `'Z'` with the enable of the entity |
| `eth_rgmii_mac` | `i_tx_clk` takes `clk_eth_tx` and `i_tx_clk_dly` takes `clk_eth_tx_dly` (or `clk_eth_tx` with `shifted_txc` false); `GTX_CLK`, `TXD` and `TX_CTL` leave directly, `RXC`, `RXD` and `RX_CTL` enter directly, and the MDIO leaves with enable |
| `lcd`, `usb_bridge`, `eth` (MDIO), `hdmi_tx` (I2C), `adxl345` (`mosi`) | Output with enable, `'Z'` when disabled, and a signal back with the read of the pin |
| `i2c_master` | Open drain, `'0'` when the entity asks for low and `'Z'` otherwise |
| `audio` | The FPGA is the master of the codec clocks, and the inputs `i_bclk`, `i_adclrck` and `i_daclrck` stay at `'0'` |
| `hdmi_audio` | Four output lines (`o_mclk`, `o_sclk`, `o_lrclk`, `o_i2s0`), the entity being the I2S master |
| `uart` | `rx` and `tx` direct; without the `cts` pin the input is tied to `'0'`, and without `rts` the output is left open |
| `usb_bridge` | `dreq` and `dack` are optional: without them `i_otg_dreq` stays at `'0'` and `o_otg_dack` open |
| `adc128s022`, `ltc2308`, `ir_receiver`, `tv`, `spi` | Straight; the `cs_n` of the `spi` is sliced to the width of the board port |

The `video` and the `hdmi_tx` receive `i_pixel_clk` from the `clk_pixel` signal, declared when the clock plan has the `pixel` output; without it (no source gives the frequency) the instance is left out with a warning. The `hdmi_tmds` kind (direct TMDS output, role `hdmi_tmds` with `tmds`, `clk`, `scl`, `sda` and optional `hpd`) is registered, but the `hdmi_tmds_tx` entity is not in `Peripherals`; the generation fails with an error that says so, and no port is invented. The dependency is the TMDS serializer of `Peripherals`, with the pixel clock and the serial clock of five times (`pixel_x5`) that the plan already makes. The `max10_adc_shell` wires `i_adc_clk_10` to the `clk10` pin (`ADC_CLK_10`), and the IP of the core enters the project through [board_generate](board_generate.md).

## 4. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_generate.py` | DE0-CV top content, latencies, pin ring, polarity and syntax accepted by GHDL |
| `tests/test_board_video_generate.py` | The video generics reach the `TopSpec` without changing the top |
| `tests/test_external_top.py` | The instance and the pins of each external kind, the open drain, the `'Z'` and what is left out of the top |
| `tests/test_eth_rgmii.py` | The RGMII MAC instance, the two PLL clocks and the Ethernet `.sdc` |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
