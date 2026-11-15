# `sdc_generator`

Gera o `.sdc` com relógios, atrasos de E/S do chip, caminhos de leitura e cruzamentos de domínio.

## 1. Função

Escreve as restrições de tempo de uma plataforma numa placa, a partir do plano de relógios, das portas, dos atrasos do chip e do padrão de nó de relógio da família.

## 2. Ordem do arquivo

| # | Bloco |
| ---: | :--- |
| 1 | `create_clock` da entrada de referência, `derive_pll_clocks` e `derive_clock_uncertainty` |
| 2 | Relógio gerado do pino da SDRAM e atrasos de E/S do chip |
| 3 | Caminho de leitura da memória (ciclo múltiplo 2 e 1) |
| 4 | Cruzamentos entre os domínios `mem`, `core` e `fetch`, e entre eles e o relógio da JTAG |
| 5 | Caminhos falsos do reset, das chaves, dos botões, dos LEDs, dos displays e dos pinos da FLASH NOR e da SRAM |

## 3. Limite dos cruzamentos

Cada cruzamento é limitado por um atraso menor que a latência do sincronizador de dois flip-flops, sem verificação de hold. O limite é o menor período entre os relógios do SoC,

$$ b = \min_{r} T_r $$

o que dá 10 ns para a DE0-CV a 50 MHz de núcleo e 100 MHz de controlador, e acompanha o período do núcleo quando ele muda.

## 4. Relógio de pixel e relógio do ADC

Com a saída `pixel` no plano, o `.sdc` declara o nó do relógio de pixel e limita os dois cruzamentos com o domínio do núcleo pelo menor entre o período do pixel e o limite da seção 3. O `pixel_x5` é só um nó a mais, no mesmo domínio relacionado ao pixel. O pino `clk` do papel `adc` (o `ADC_CLK_10` do MAX 10) vira um `create_clock` com o período da entrada da placa e um grupo de relógios assíncrono aos demais.

## 5. Nó dos relógios do PLL

O nome do nó vem do campo `pll.clock_node_pattern` da família, com `<instance>` e `[N]`, trocados pelo nome da instância do PLL e pelo índice da saída. Uma família sem o padrão (`altpll` ainda sem medição) falha com `SdcError`.

## 6. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_video_clocks.py` | O domínio do relógio de pixel, os cruzamentos e o `create_clock` do `ADC_CLK_10` |
| `tests/test_board_equivalence.py` | O `.sdc` gerado da DE0-CV tem as restrições do `de0-cv.sdc` escrito à mão |
| `tests/test_board_generate.py` | `.sdc` das placas com PLL de teste |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
