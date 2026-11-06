# `board_clocks`

Decide os relógios por papel (`mem`, `mem_pin`, `fetch`, `core`) com frequência e fase.

## 1. Função

O PLL, o `.sdc` e o topo leem o mesmo plano, de modo que cada relógio é decidido uma só vez.

## 2. Origem de cada valor

| Papel | Frequência | Fase |
| :--- | :--- | :--- |
| `core` | `clocks.core.mhz` da plataforma | `clocks.core.phase_ps` |
| `fetch` | `clocks.fetch.mhz`; sem o campo o papel usa o relógio do `core` | `clocks.fetch.phase_ps` |
| `mem` | O menor entre `clocks.mem.mhz` e o `max_mhz` dos chips usados; acima do teto é erro V7 | 0 |
| `mem_pin` | A do `mem` | `memories.sdram.clk_phase_ps` da placa; `null` vira 0 com aviso |

`mem` e `mem_pin` só existem com um backend `dispositivo` (`mem_pin` só com SDRAM). A ordem das saídas do PLL é `mem`, `mem_pin`, `fetch`, `core`, e o nome da instância do PLL é `pll_inst` em todos os topos, de modo que o `.sdc` não varia com ele.

## 3. Período mínimo

`min_period_ns` é o menor período entre os relógios do SoC e limita os cruzamentos de domínio do `.sdc`.

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_ports.py` | Plano de relógios da DE0-CV, teto do chip (V7) e fase não medida |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
