# `board_clocks`

Decide os relógios por papel (`mem`, `mem_pin`, `fetch`, `core`, `eth_tx`, `eth_tx_dly`, `pixel`, `pixel_x5`) com frequência e fase.

## 1. Função

O PLL, o `.sdc` e o topo leem o mesmo plano, de modo que cada relógio é decidido uma só vez.

## 2. Origem de cada valor

| Papel | Frequência | Fase |
| :--- | :--- | :--- |
| `core` | `clocks.core.mhz` da plataforma | `clocks.core.phase_ps` |
| `fetch` | `clocks.fetch.mhz`; sem o campo o papel usa o relógio do `core` | `clocks.fetch.phase_ps` |
| `mem` | O menor entre `clocks.mem.mhz` e o `max_mhz` dos chips usados; acima do teto é erro V7 | 0 |
| `mem_pin` | A do `mem` | `memories.sdram.clk_phase_ps` da placa; `null` vira 0 com aviso |
| `eth_tx` | 125 MHz, o relógio livre do envio do Ethernet RGMII | 0 |
| `eth_tx_dly` | 125 MHz, o relógio que sai por `GTX_CLK`, deslocado de um quarto de ciclo | 2000 ps |
| `pixel` | O `pixel_clock_mhz` do modo resolvido de `io.video`, ou o `pixel_clock_khz` escrito no periférico; os dois têm de coincidir | 0 |
| `pixel_x5` | Cinco vezes o `pixel`, só quando um periférico pede o relógio serial (TMDS) | 0 |

`mem` e `mem_pin` só existem com um backend `dispositivo` (`mem_pin` só com SDRAM). `eth_tx` existe quando alguma entrada `eth` tem `mode: rgmii`, e `eth_tx_dly` só quando alguma delas deixa `shifted_txc` em verdadeiro (o padrão); com `shifted_txc` falso o PHY insere o atraso e o `GTX_CLK` sai do próprio `eth_tx`. `pixel` e `pixel_x5` só existem quando um periférico externo tem a porta do relógio de pixel e uma das duas fontes dá a frequência; sem isso o PLL não ganha a saída. A ordem das saídas do PLL é `mem`, `mem_pin`, `fetch`, `core`, `eth_tx`, `eth_tx_dly`, `pixel`, `pixel_x5`, e o nome da instância do PLL é `pll_inst` em todos os topos, de modo que o `.sdc` não varia com ele.

## 3. Período mínimo

`min_period_ns` é o menor período entre os relógios do SoC (sem `mem_pin`, `eth_tx`, `eth_tx_dly`, `pixel` e `pixel_x5`) e limita os cruzamentos de domínio do `.sdc`. Os relógios do vídeo ficam fora do mínimo, porque formam um domínio próprio (seção 4 de [sdc_generator](sdc_generator.md)).

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_ports.py` | Plano de relógios da DE0-CV, teto do chip (V7) e fase não medida |
| `tests/test_eth_rgmii.py` | Os pedidos de relógio do RGMII, com e sem o deslocamento do `GTX_CLK` |
| `tests/test_video_clocks.py` | Saída `pixel` e `pixel_x5` do PLL, período mínimo sem os relógios de vídeo, fonte da frequência e recusa de divergência |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
