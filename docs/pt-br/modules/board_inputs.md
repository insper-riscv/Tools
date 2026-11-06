# `board_inputs`

Lê o `platform.yaml`, o `board.yaml`, o `pins.yaml`, a família e os chips que um gerador consome.

## 1. Função

Reúne num só objeto (`BoardInputs`) os arquivos de dados de uma plataforma numa placa. Lê só os campos que os geradores usam e recusa o que falta com uma mensagem que nomeia o arquivo. A validação completa de tipos é a do módulo de esquemas e o substitui sem mudar quem o chama.

## 2. Arquivos lidos

| Arquivo | Onde é procurado |
| :--- | :--- |
| `platform.yaml` | Caminho dado |
| `board.yaml` e `pins.yaml` | `<boards>/<placa>/` |
| Família | `<boards>/families/<família>.yaml` |
| Chip | `<chips>/<chip>.yaml`, com a cadeia `extends` mesclada em profundidade e ciclo recusado |

## 3. Escolha da placa

A placa vem da linha de comando, do campo `board` da plataforma ou da única entrada de `boards`. Com várias entradas e `board: auto`, o pedido falha pedindo `--board`. A função `board_idcode` devolve o IDCODE da entrada `fpga: true` da cadeia JTAG, que o `program --board` usa para escolher o cabo.

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_inputs.py` | Carga das seis placas, herança de chip, ciclo, escolha da placa, V1 e IDCODE |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
