# `ram_target`

Onde fica a RAM de um projeto e como o host a alcança por JTAG. `mailbox`, `ram_dump` e `ram_zero` recebem um alvo de RAM e chamam este módulo, então funcionam com os dois tipos de RAM.

| Alvo | A RAM é | Alcançada por |
| :--- | :--- | :--- |
| um `int` | uma instância de memória dentro da FPGA | [`mem_edit`](mem_edit.md), pelo índice da instância |
| `SdramDebugRam` | a SDRAM | [`sdram_debug`](sdram_debug.md) |

`target_from_config(cfg)` escolhe um a partir de `quartus.ram_backend` (`ismce`, o padrão, com `quartus.ram_mem_instance`, ou `sdram_debug`).

Uma RAM de 64 MB não cabe num dump inteiro por JTAG, e o golden só confere poucas palavras. Para a SDRAM, o `ram_dump` salva um `.mif` esparso com só as palavras que o golden nomeia (`mem_validator.golden_word_offsets`), que o `mem_validator` lê como qualquer outro dump. `riscv-tools dump-ram --start-word N --words M` faz o mesmo à mão.

## Testes

`tests/test_sdram_debug.py`.

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
