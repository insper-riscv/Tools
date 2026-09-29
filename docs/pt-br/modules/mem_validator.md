# `mem_validator`

Compara um dump de RAM (um `.mif`, uma palavra de 32 bits por linha, veja [`ram_dump`](ram_dump.md)) com um golden JSON de valores de byte esperados. Usado nos testes `RV32_TEST_KIND: memory`, em que só o mailbox PASS/FAIL não basta para provar que um teste fez a coisa certa: que ele escreveu os valores certos na memória, e não apenas chegou ao próprio sinal de sucesso.

## Formato do golden JSON

Um objeto JSON plano que mapeia strings de endereço de byte para valores de byte esperados (0-255), por exemplo `{"0": 18, "1": 52, "2": 86}`. Produzido à mão e versionado no diretório do próprio teste, ou gerado dinamicamente pelo [`golden_generator`](golden_generator.md) ao rodar o teste no Spike.

## Configuração

Nenhuma: recebe o caminho do dump e o caminho do golden JSON como argumentos diretos; não tem seção própria no `config.yaml`.

## Testes

Não há teste automatizado neste repositório. A execução em hardware real de um projeto consumidor e o testbench de simulação dele comparam a memória com goldens usando este módulo.

## Uso

Não é um subcomando próprio da CLI: é chamado internamente pelo [`orchestrator`](orchestrator.md) logo depois do [`ram_dump`](ram_dump.md), para todo teste do tipo `memory` numa suíte.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
