# `top_generator`

Gera o topo fino da placa, que só liga o PLL, o SoC, um backend por região e o anel de pinos.

## 1. Função

O topo gerado não tem lógica além do reset. Ele liga, nesta ordem, as portas da placa, o PLL, a normalização de polaridade dos papéis de E/S (K8), a instância do SoC, uma instância de backend por região externa e o anel de pinos de três estados.

## 2. Conteúdo

| Parte | Origem |
| :--- | :--- |
| Generics `HPM_COUNTERS` e `HPM_WIDTH` | Presentes quando o perfil tem Zihpm, repassados ao SoC |
| Reset | Reset do usuário normalizado para ativo em `'1'`, reset do SoC liberado dois ciclos de `core` depois do PLL travar |
| Polaridade | `not` em chaves, botões, LEDs e displays de papel `active: low` |
| Backend `emulado` | Tamanho da região, `latency.first` e `latency.next`, `sector_bytes` |
| Backend `dispositivo/sdram` | Largura de `DQ_WIDTH` pelas portas, e um `tristate_buffer_1bit` por bit do dado em um `generate` |
| Backends `sram` e `nor` | Uma ligação por porta da placa |

## 3. Contrato com o SoC e os backends

Os nomes da entidade do SoC (`soc`), dos backends e de suas portas ficam todos em constantes do módulo, de modo que ajustá-los às entidades publicadas pelo Core e pelo Memory é uma troca em um arquivo.

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_generate.py` | Conteúdo do topo da DE0-CV, latências, anel de pinos, polaridade e sintaxe aceita pelo GHDL |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
