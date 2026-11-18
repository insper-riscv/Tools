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
| 5 | Relógios do Ethernet RGMII: `RXC` de 125 MHz como relógio de entrada, `GTX_CLK` como relógio gerado do nó do PLL, grupo assíncrono ao SoC e caminhos falsos de MDC, MDIO, INT_N e RESET_N |
| 6 | Relógio `ADC_CLK_10` de 10 MHz do ADC do MAX 10, com o grupo assíncrono ao SoC |
| 7 | Relógio `CLK` da câmera MIPI como relógio de entrada de 200 MHz (teto de 400 Mbit/s por lane), com o grupo assíncrono ao SoC |
| 8 | Caminhos falsos dos pinos do módulo Wi-Fi, que são lentos e assíncronos ao núcleo |
| 9 | Caminhos falsos dos pares e do `hpd` da saída HDMI com TMDS direto, que saem do registrador DDR do relógio serial e não têm requisito de tempo |
| 10 | Caminhos falsos do reset, das chaves, dos botões, dos LEDs, dos displays e dos pinos da FLASH NOR e da SRAM |

## 3. Limite dos cruzamentos

Cada cruzamento é limitado por um atraso menor que a latência do sincronizador de dois flip-flops, sem verificação de hold. O limite é o menor período entre os relógios do SoC,

$$ b = \min_{r} T_r $$

o que dá 10 ns para a DE0-CV a 50 MHz de núcleo e 100 MHz de controlador, e acompanha o período do núcleo quando ele muda.

## 4. Relógio de pixel

Com a saída `pixel` no plano, o `.sdc` declara o nó do relógio de pixel e limita os dois cruzamentos com o domínio do núcleo pelo menor entre o período do pixel e o limite da seção 3. O `pixel_x5` é um nó a mais, do mesmo PLL, e entra no mesmo conjunto `video_clocks` do pixel, de modo que os dois cruzamentos com o núcleo valem para os dois relógios.

## 5. Nó dos relógios do PLL

O nome do nó vem do campo `pll.clock_node_pattern` da família, com `<instance>` e `[N]`, trocados pelo nome da instância do PLL e pelo índice da saída. Uma família sem o padrão (`altpll` ainda sem medição) falha com `SdcError`.

Duas saídas do PLL com a mesma frequência e a mesma fase são o mesmo relógio, e o Quartus as funde na de menor índice; o `.sdc` cita o nó dessa saída para todos os papéis envolvidos, e o cruzamento entre o controlador e o núcleo deixa de fora o domínio que coincide com o do controlador.

## 6. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_video_clocks.py` | O domínio do relógio de pixel, os cruzamentos |
| `tests/test_board_equivalence.py` | O `.sdc` gerado da DE0-CV tem as restrições do `de0-cv.sdc` escrito à mão |
| `tests/test_board_generate.py` | `.sdc` das placas com PLL de teste |
| `tests/test_top_generics_and_clocks.py` | A conversão das tabelas de janelas, o piso de 6 fontes do PLIC, chaves e botões só com janela e o nó do relógio fundido do PLL |
| `tests/test_eth_rgmii.py` | O bloco do Ethernet RGMII e o limite dos cruzamentos sem os relógios dele |
| `tests/test_external_top.py` | O relógio da câmera MIPI e o grupo assíncrono, e os caminhos falsos do módulo Wi-Fi e da saída TMDS |
| `tests/test_vendor_ip.py` | O relógio do ADC, o IP e o script no projeto, o `dreq` e o `dack` do USB e a regra V25 |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
