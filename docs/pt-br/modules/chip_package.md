# `chip_package`

Gera o pacote VHDL com os tempos de um chip do catálogo e entrega os atrasos de E/S ao `.sdc`.

## 1. Função

Os tempos de um chip existem só no seu arquivo do catálogo. Este módulo os escreve como pacote VHDL `chip_<chip>_pkg` (um por chip usado pela placa), lido pelo controlador e pelo modelo, e como atrasos de E/S para o `.sdc`.

## 2. Constantes

As chaves `t<nome>_<unidade>` do catálogo viram `T_<NOME>_<UNIDADE>` (`trcd_ps` vira `T_RCD_PS`), com os mesmos nomes que o `sdram_pkg.vhd` tem hoje. As demais viram o nome em maiúsculas.

| Origem | Constantes |
| :--- | :--- |
| `timing` | Uma por tempo, arredondada para cima |
| `organization` | `ROW_BITS`, `COL_BITS`, `DQ_WIDTH` |
| Raiz do chip | `SECTOR_BYTES`, `BOOT_SECTOR_BYTES` quando existem |
| SDRAM | `CAS_LATENCY`, `BANK_BITS` e `MODE_REG` |

O registrador de modo é $A_{2:0} = \log_2 B$ para a rajada $B$, $A_{3} = 0$ (sequencial) e $A_{6:4} = CL$. A rajada vale $32 / (n_{chips} \cdot w)$, e para um chip de 16 bits a rajada de 2 reproduz `0000000110001`. Uma SDRAM sem algum dos onze tempos obrigatórios é recusada.

## 3. Atrasos de E/S

`chip_io_delays` devolve os quatro atrasos do `.sdc` a partir de `io_timing`.

| Atraso | Origem |
| :--- | :--- |
| Saída máxima | `input_setup_ns` |
| Saída mínima | $-$`input_hold_ns` |
| Entrada máxima | `access_ns` |
| Entrada mínima | `output_hold_ns` |

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_chip_package.py` | Nomes e valores iguais aos do `sdram_pkg.vhd`, registrador de modo por rajada, organização, NOR, tempo ausente e atrasos do `.sdc` |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
