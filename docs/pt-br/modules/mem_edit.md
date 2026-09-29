# `mem_edit`

Primitivas genéricas do In-System Memory Content Editor, compartilhadas por [`rom_writer`](rom_writer.md), [`ram_zero`](ram_zero.md), [`ram_dump`](ram_dump.md) e [`mailbox`](mailbox.md). Só mecanismo, sem política: cada um desses módulos decide qual instância, endereço ou conteúdo usar; este módulo só sabe ler e escrever uma instância de memória por JTAG.

## Funções

| Função | O que faz |
| :--- | :--- |
| `write_full` | Sobrescreve a profundidade inteira de uma instância de memória a partir de um `.mif`. |
| `write_full_multi` | O mesmo, mas escreve o mesmo `.mif` em várias instâncias numa só chamada (um design com mais de uma cópia física do mesmo conteúdo, mantidas em sincronia). |
| `write_word` | Sobrescreve uma única palavra num dado offset. |
| `read_words` | Lê de volta um intervalo de palavras. |
| `dump` | Salva o conteúdo inteiro de uma instância num `.mif`. |

## Configuração

Nenhuma: recebe um `JtagLink` (veja [`jtag`](jtag.md)), um índice de instância e caminhos/endereços como argumentos diretos; não tem seção própria no `config.yaml`. Quem o chama decide qual índice de instância e profundidade se aplicam ao próprio caso de uso.

## Pré-requisitos

- O Quartus Prime Lite no `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), instalado como no `QUARTUS_INSTALL.md` do Infra, e uma placa com um USB-Blaster conectado por JTAG, com as instâncias do In-System Memory Content Editor que o design do projeto expõe.

## Testes

Não há teste automatizado neste repositório. Um runner self-hosted preparado como no `RUNNER_SETUP.md` do Infra roda a suíte de hardware real de um projeto consumidor (`riscv-tools run`), que é o único lugar onde este módulo é exercitado.

## Uso

Não é um subcomando próprio da CLI: é o mecanismo que [`rom_writer`](rom_writer.md), [`ram_zero`](ram_zero.md), [`ram_dump`](ram_dump.md) e [`mailbox`](mailbox.md) chamam para de fato conversar com uma instância de memória por JTAG.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
