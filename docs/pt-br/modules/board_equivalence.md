# `board_equivalence`

Compara o projeto gerado com os arquivos escritos à mão: pinos, restrições, PLL, fontes e atribuições.

## 1. Função

Mostra o que a geração perde, muda ou acrescenta contra os arquivos de hoje, sem substituí-los. A comparação é normalizada.

## 2. Seções

| Seção | Comparação |
| :--- | :--- |
| `pins` | Conjunto de (sinal, pino, padrão de E/S) do `.qsf` |
| `assignments` | Atribuições por instância que não são padrão de E/S, com trocas de texto opcionais (o nome do módulo do PLL) |
| `project` | `FAMILY`, `DEVICE`, `VHDL_INPUT_VERSION`, `OPTIMIZATION_MODE` e `SEED` |
| `sources` | Nomes dos arquivos de fonte, menos os de `ignored_sources` |
| `constraints` | Comandos do `.sdc` com as variáveis `set` expandidas e os conjuntos entre chaves ordenados |
| `pll` | Frequência, fase e razão contra a referência de cada saída |

Cada seção lista o que só existe à mão, o que só existe no gerado e o que mudou. O relatório é equivalente quando nada só existe à mão e nada mudou; o que só existe no gerado é acréscimo.

## 3. Resultado na DE0-CV

Contra o `de0-cv.qsf`, o `de0-cv.sdc` e o `sdram_platform_pll.v` de hoje, `pins`, `assignments`, `project`, `constraints` e `pll` são equivalentes. São 107 pinos atribuídos. O gerado acrescenta dois caminhos falsos (chaves e botões, que o topo atual não liga). `sources` só difere pelo topo, pelo PLL, pelo pacote do chip e pelas fontes do fecho dos `provides`.

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_equivalence.py` | DE0-CV gerada contra os arquivos reais (fixtures), contagem de pinos, acréscimos e detecção de pino, fase e atraso alterados |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
