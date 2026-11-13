# `board_inputs`

Lê o `platform.yaml`, o `board.yaml`, o `pins.yaml`, a família e os chips que um gerador consome.

## 1. Função

Reúne num só objeto (`BoardInputs`) os arquivos de dados de uma plataforma numa placa. A leitura e a validação de `board.yaml`, `pins.yaml`, família e chip são as do `board_schema` (`Catalog`); este módulo escolhe a placa, carrega o que a plataforma usa e entrega os registros tipados como mapas (`board_view`, `family_view`, `chip_view`) que os geradores consomem. Um erro do catálogo vira `InputError`.

## 2. Arquivos lidos

| Arquivo | Onde é procurado |
| :--- | :--- |
| `platform.yaml` | Caminho dado |
| `board.yaml` e `pins.yaml` | `<boards>/<placa>/` |
| Família | `<boards>/families/<família>.yaml` |
| Chip | `<chips>/<chip>.yaml`, só os chips de tempo (`sdram`, `sram`, `nor`), com `extends` resolvido pelo catálogo |
| `video-modes.yaml` | `<boards>/video-modes.yaml`, só quando a placa tem `io.video` |

## 3. Escolha da placa

A placa vem da linha de comando, do campo `board` da plataforma ou da única entrada de `boards`. Com várias entradas e `board: auto`, o pedido falha pedindo `--board`.

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_inputs.py` | Carga das seis placas, herança de chip, chips de tempo, escolha da placa e V1 |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
