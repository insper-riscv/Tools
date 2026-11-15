# `board_video`

Resolves the video that a platform asks for on a board: it chooses the mode and checks the proportion, the color channel width, the pixel clock and the framebuffer, and hands the timing generics to the generated top.

## 1. Purpose

The board package declares what the video output offers (`io.video` of the `board.yaml`), the catalog `boards/video-modes.yaml` keeps the timing of each mode once, and the platform asks for what it wants in `io.video` of the `platform.yaml`. This module joins the three and produces a `VideoPlan`, with the mode, the channel width and the framebuffer size. The three files are read by [board_schema](board_schema.md).

## 2. Mode choice

The table lists the requests in order of precedence.

| Platform request | Mode chosen |
| :--- | :--- |
| No `io.video`, or an empty `io.video` | The `default_mode` of the board |
| Only `aspect` | The mode of largest area, among the `modes` of the board, that has that proportion; on a tie, the lowest refresh rate |
| `width` and `height` | The catalog mode of that size; among different rates, the `default_mode`, then a mode the board lists, then the lowest rate |
| `width`, `height` and `aspect` | As `width` and `height`, and the proportion of the mode must be the requested one |
| `refresh_hz` with a size or a proportion | Narrows the candidates to the requested rate |

A platform that lists the `VIDEO` peripheral in `peripherals` and does not write `io.video` asks for the default mode. The proportion of a mode is the ratio of width to height in lowest terms, so `1280x1024` is `5:4` and neither accepted proportion covers it.

## 3. Checks

| Rule | Error when |
| :--- | :--- |
| V20 | The mode is not in the catalog, the proportion does not match `width` and `height`, the mode is not in `modes` of the board and `outside_manual: true` is missing, the requested `channel_bits` exceeds the board value, the framebuffer is larger than the visible area or the board has no `io.video` |
| V21 | The PLL of the board cannot make the pixel clock together with the clocks of the platform |
| V22 | The framebuffer does not fit the memory blocks the rest of the platform leaves free |

With `outside_manual: true` a mode outside `modes` becomes the V20 warning, because the monitor may not accept it.

### 3.1. Pixel clock

The pixel clock is one more output of the PLL that already makes the clocks of the `platform.yaml`, so the check solves them all together with the calculation of [pll_generator](pll_generator.md) (a single VCO, integer dividers, the number of outputs of the family). The message says whether the pixel clock already fails alone from the reference of the board or whether the conflict is with the other clocks.

### 3.2. Framebuffer

The pixel format is `pixel_format` of `io.video`, and the default is `indexed`. Each format stores the bits of the table below, and the peripheral writes the framebuffer in 32-bit words, with each line rounded up to whole words.

| `pixel_format` | Bits per pixel | Palette |
| :--- | ---: | :--- |
| `indexed` | 8 | 256 entries of $3 \cdot \text{channel\_bits}$ bits |
| `direct` | 16 if $3 \cdot \text{channel\_bits} \le 16$, else 32 | none |

The framebuffer and the palette take

$$
\left\lceil \frac{\text{fb\_height} \cdot \left\lceil \text{fb\_width} \cdot \text{bits} / 32 \right\rceil \cdot 32 + 256 \cdot 3 \cdot \text{channel\_bits}}{\text{bits\_per\_block}} \right\rceil
$$

memory blocks, without the palette term in the `direct` format. The free amount is the capacity of the board minus the blocks that the estimate of [fit_estimate](fit_estimate.md) gives for the profile. Without the calibration table of the family, the check compares with the total of the device. Without `fb_width` and `fb_height` the framebuffer has the visible area of the mode.

The framebuffer takes the upper half of the window of the peripheral, $2^{15}$ words (128 KiB), and V22 also rejects a framebuffer that exceeds it (the 640x480 indexed one, of 300 KiB, does not fit, and the 320x200 one does).

The `scale` of `io.video` is the enlargement of each framebuffer pixel. Without it, the largest whole enlargement that fits the image in the visible area is used, and a larger value is a V20 error.

## 4. Generics for the top

`VideoPlan.generics()` writes the associations below, and `top_generator.video_generics` hands them over from the `TopSpec`. The `Generated` of `board_generate` carries the plan in `video`.

| Generic | Value |
| :--- | :--- |
| `video_kind` | `"vga"` or `"hdmi"` |
| `video_channel_bits` | 4 or 8 |
| `video_fb_width`, `video_fb_height` | Framebuffer size |
| `video_pixel_format`, `video_scale` | `"indexed"` or `"direct"`, and the pixel enlargement |
| `video_h_visible`, `video_h_front_porch`, `video_h_sync`, `video_h_back_porch`, `video_h_total` | Horizontal timing, in pixels |
| `video_v_visible`, `video_v_front_porch`, `video_v_sync`, `video_v_back_porch`, `video_v_total` | Vertical timing, in lines |
| `video_h_sync_positive`, `video_v_sync_positive` | `true` when the synchronism pulse is high |

The `video` peripheral of the generated top receives the generics of the entity, with its names and without the `video_` prefix, written by `VideoPlan.entity_generics()`: `fb_width`, `fb_height`, `channel_bits`, `pixel_format`, `scale` and, for each direction, `h_` and `v_` followed by `visible`, `front_porch`, `sync`, `back_porch` and `sync_positive`. The generic map of the SoC does not receive the generics above.

## 5. Pixel clock

When an external peripheral with the pixel clock port (`video`, `hdmi` or `hdmi_tmds`) is in `peripherals`, the `board_generate` resolves the video and asks the PLL for the `pixel` output, with the frequency of the mode. The top declares the `clk_pixel` signal and wires the `i_pixel_clk` of the entities, and the `.sdc` treats the pixel as its own domain.

## 6. Tests

| Test | What it checks |
| :--- | :--- |
| `tests/test_board_video.py` | Reading of the `video` role and of the catalog of modes, the platform request (including `16:9` without quotes), the mode choice, the rules V20 to V22, the generics and the catalog check |
| `tests/test_board_video_generate.py` | The plan reaches `Generated`, the generated top does not change, the generics come out of the `TopSpec` and the generator refuses an impossible request |
| `tests/test_video_clocks.py` | The `pixel` PLL output, the signal and wiring in the top, the `.sdc` domain, the source of the frequency and the refusal of `hdmi_tmds` |
| `tests/test_external_top.py` | The `video` peripheral gets the generics of the entity, with the video plan and the pixel format |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
