# Identificação da placa no laboratório

## 1. Referência

Este documento registra a observação, em hardware, dos nove casos de ambiguidade da seção 5 do documento `03-IDENTIFICACAO-PELO-JTAG.md` do plano Multi-FPGA, com os subcomandos `riscv-tools board scan`, `select`, `lock` e `doctor` descritos em [`board`](modules/board.md). Os comandos só leem: nenhuma placa foi programada, e nenhum cabo foi tocado.

## 2. Hardware e método

| Host | Cabos | Porta USB (`ID_PATH`) |
| :--- | :--- | :--- |
| Notebook | DE0-CV `02B050DD` | `pci-0000:00:14.0-usb-0:6` |
| PC1 | DE0-CV `02B050DD` | `pci-0000:00:14.0-usb-0:2` |
| PC1 | DE2-115 `020F70DD` | `pci-0000:00:14.0-usb-0:3` |
| PC1 | DE0-Nano `020F30DD` | `pci-0000:00:14.0-usb-0:5` |
| PC1 | DE10-Lite `031050DD` | `pci-0000:00:14.0-usb-0:6` |
| PC1 | MKR Vidor 4000, só `2341:8056` na USB | sem cabo |

A DE10-Nano não enumera, e por isso só entra por fixture. Os quatro cabos da PC1 apresentam o mesmo `iSerial` (`91d28408`) e portas diferentes, o que confirma que o número de série não identifica a placa e que o `ID_PATH` identifica.

Cada caso tem uma de duas origens.

| Origem | Significado |
| :--- | :--- |
| Real | A saída do `jtagconfig` e da USB é a do hardware ligado |
| Simulada | Um `jtagconfig` de empacotamento troca no texto real só a linha do cabo afetado (outro IDCODE, cadeia quebrada, cabo ausente), porque o laboratório não tem a segunda placa igual no mesmo host nem como quebrar uma cadeia sem mexer no cabo físico. O cabo, a porta e a leitura do `udev` continuam reais |

## 3. Os nove casos

| # | Caso | Origem | Comando | Resultado observado |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Um cabo, uma candidata | Real | `board select` no notebook | `de0-cv`, id `de0-cv-laptop`, saída 0 |
| 2 | Duas placas iguais no mesmo host | Simulada | `board select` com `[1-3]` mostrando `02B050DD` | Erro de caso 2 com a lista dos cabos e das portas; `--board-id`, `--cable` e `--free` desempatam; `scan --save` numera a segunda como `de0-cv-ws-2` |
| 3 | Placas iguais em hosts diferentes | Real | `board select` no notebook e na PC1 | Cada host escolhe a sua DE0-CV; o id leva o nome do host (`de0-cv-laptop`, `de0-cv-ws`) e a trava também (`de0cv-laptop.lock`, `de0cv-ws.lock`) |
| 4 | Mesmo IDCODE de dispositivos diferentes | Real | `board select --board de2-115`, `de0-nano` | Escolhidas pelo IDCODE, com o aviso de que `020F70DD` e `020F30DD` não provam a variante |
| 5 | Mesmo dispositivo em placas diferentes | Fixture | `pytest tests/test_board_scan_select.py` | `--board` ou o inventário desempata; o laboratório só tem uma placa por IDCODE de EP4CE22 |
| 6 | Revisões do mesmo dispositivo | Real | `board select --board de10-lite` | Aviso de que `031050DD` não distingue `10M50DA` de `10M50DC` |
| 7 | IDCODE desconhecido ou placa ausente | Real e simulada | `--board de2-115` no notebook; cabo `[1-3]` removido; IDCODE `0123ABCD` | Erro de caso 7 com os IDCODEs procurados e os cabos vistos; com inventário, `no cable at <porta>` ou `IDCODE mismatch`; sem nenhum cabo, `searched IDCODEs ...; cables seen: no cable` |
| 8 | Cadeia quebrada | Simulada | `board scan`, `select`, `doctor` | `scan` marca o problema na porta e as outras placas seguem selecionáveis; `select --board de2-115` falha com caso 8; `doctor` pede desligar a placa por 10 s e religar |
| 9 | Cabo ocupado | Real | `board lock` em dois processos, `quartus_stp` estranho | Ver a seção 5 |

## 4. Seleção

Todos os resultados abaixo vêm da PC1 com as quatro placas ligadas e do notebook com uma.

| Forma | Observado |
| :--- | :--- |
| Sem opção, quatro placas distintas | Erro de caso 2: `4 boards match`, com placa, cabo e porta de cada uma |
| `--board <nome>` | Cada uma das quatro escolhe o cabo certo; `--board mkr-vidor-4000` e `--board de10-nano` falham em caso 7 |
| `--cable "<nome>"` | Escolhe a placa pelo IDCODE do cabo; um cabo inexistente falha em caso 7, e `--cable` do DE0-CV com `--board de2-115` falha com `expects IDCODE 020F70DD ... the chain has 02B050DD` |
| `--board-id <id>` | Escolhe a entrada do inventário; id desconhecido lista os ids conhecidos |
| `--platform` | `board: auto` com `boards: [de2-115]` escolhe a DE2-115; `--board` vence o campo da plataforma; a plataforma da Vidor falha em caso 7 |
| Precedência | `--board-id` vence `--board`; `--cable` vence o inventário, mas o IDCODE do cabo ainda é conferido contra a placa pedida por `--board` |
| `--free` | Escolhe a primeira placa livre pela ordem das portas, nunca pela ordem do `jtagconfig` |

## 5. Trava com dono e disputa

A trava foi testada com dois e três processos, numa pasta de travas isolada (`lock_dir`), para não competir com os agentes que seguram `/tmp/de0cv-*.lock`.

| Situação | Resultado |
| :--- | :--- |
| O processo A segura a DE0-CV com `--hold` | O arquivo de trava guarda host, usuário, processo, comando e instante |
| B pede a mesma placa sem `--wait` | Falha na hora com caso 9, o dono (`usuario@host`, pid, desde quando) e o comando dele; saída 3 |
| B pede a mesma placa com `--wait 3` | Espera os 3 s e falha com o mesmo dono |
| B pede a mesma placa com `--wait 20` e o dono solta em 5 s | Entra após 5,5 s |
| C pede a DE10-Lite enquanto A segura a DE0-CV | Entra: a trava é por placa, não por cabo nem por host |
| Dono é um `flock` comum | Falha com `held by an owner that did not record itself (a plain flock)` |
| `select` enquanto a placa está ocupada | Erro de caso 9 com o dono, ou `free: false` com `--all` |
| `doctor` enquanto a placa está ocupada | Mostra o dono da trava |
| Processo `quartus_stp` estranho em execução | `doctor` avisa `process <pid>` com a dica do caso 9 |

## 6. Cabo trocado de porta

O `ID_PATH` é a chave, e o nome do cabo é só o argumento de `-c`. Duas trocas foram simuladas no inventário, com os cabos reais da PC1 nas portas de sempre.

| Troca | Resultado |
| :--- | :--- |
| O cabo da DE2-115 aparece em `:3` e o inventário a tem em `:7` | O cabo em `:3` aparece sem entrada, `select --board de2-115` o acha pelo IDCODE, `--board-id` falha com `no cable at :7`, `doctor` avisa as duas portas, e `scan --save` troca a porta da entrada existente sem criar uma segunda |
| DE0-CV e DE2-115 trocadas de porta | Falha de `IDCODE mismatch` nas duas portas, em `scan`, `select --board-id` e `doctor` (regra V17), sem escolher a placa errada |

## 7. O que o laboratório não cobre

| Item | Motivo |
| :--- | :--- |
| Duas DE0-CV no mesmo host | As duas placas estão em hosts diferentes; o caso 2 foi simulado e está em teste de fixture |
| Cadeia quebrada de verdade | Exige mexer na alimentação ou no cabo da placa |
| Mudar o cabo de porta fisicamente | Exige mexer no cabo; a troca foi simulada no inventário |
| DE10-Nano e Vidor com cadeia | A DE10-Nano não enumera, e a Vidor só mostra a USB do SAMD21; os dois casos estão em teste de fixture |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../LICENSE).
