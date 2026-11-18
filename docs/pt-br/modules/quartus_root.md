# `quartus_root`

Localiza o Quartus instalado na máquina e põe as ferramentas dele no `PATH` do `riscv-tools`.

## 1. Função

O Quartus Prime Lite fica numa pasta por versão, em `/opt/altera_lite/<versão>/quartus/bin`. Ao iniciar, o `riscv-tools` acrescenta essa pasta ao `PATH` do próprio processo, de modo que `quartus_sh`, `quartus_pgm`, `quartus_stp` e `jtagconfig` ficam alcançáveis pelos subprocessos sem que o usuário edite o `PATH`.

## 2. Variáveis de ambiente

| Variável | Efeito | Padrão |
| :--- | :--- | :--- |
| `QUARTUS_ROOT` | Pasta que guarda as versões do Quartus | `/opt/altera_lite` |
| `QUARTUS_VERSION` | Versão dentro dessa pasta | `25.1std` |

Uma variável vazia vale como não definida.

## 3. Ordem no `PATH`

| Situação | Onde a pasta entra |
| :--- | :--- |
| `QUARTUS_ROOT` definida pelo usuário | No começo, e vence um Quartus que o `PATH` já tenha |
| `QUARTUS_ROOT` ausente | No fim, e só serve quando nenhum outro Quartus fornece as ferramentas |

A pasta só é acrescentada se existir e se o `PATH` ainda não a listar.

## 4. Uso pelo script `rt`

O script `rt` de um projeto lê as mesmas duas variáveis, monta `QUARTUS_ROOT` somente leitura no contêiner e repassa as duas ao `riscv-tools` de dentro dele. O módulo `project` descreve o script.

## 5. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_quartus_root.py` | Pasta padrão, variáveis, variável vazia, ordem no `PATH`, pasta ausente e repetição |
| `tests/test_project.py` | O `rt` usa `QUARTUS_ROOT` e `QUARTUS_VERSION` |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
