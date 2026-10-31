# `htif`

Lê o `tohost` do HTIF, a palavra de 64 bits em que um teste escreve o resultado ao terminar, e escreve no `fromhost` para dizer ao núcleo parado que reinicie a partir do ponto de entrada. Também gera o `rv32_test.h`, o header C que um teste inclui para terminar, a partir do `config.yaml` do próprio projeto (assim o projeto consumidor nunca escreve à mão nem mantém uma cópia que poderia sair de sincronia com o seu `memory.tohost_addr` real).

## Convenção do `tohost`

A palavra baixa de `tohost` vale `0` enquanto o teste roda. Um teste que passou escreve `1`. Um teste que falhou escreve `(código << 1) | 1`, com `código` diferente de zero, e o número da chamada `RV32_FAIL(código)` que falhou fica na palavra. O host reconhece o fim pelo bit 0 em `1`. O `fromhost` fica 8 bytes acima de `tohost`, e o reinício é um valor diferente de zero escrito nele.

## Offsets de palavra: relativo versus absoluto

Um endereço de byte pode ser convertido em offset de palavra de duas formas diferentes e não intercambiáveis sempre que `ram_base != 0`:

| Modo | Fórmula | Usado por |
| :--- | :--- | :--- |
| Relativo (padrão) | `(addr - ram_base) // 4` | As primitivas JTAG do [`mem_edit`](mem_edit.md), já que o In-System Memory Content Editor endereça a RAM pelo próprio índice interno de palavra, a partir de 0, e não pelo endereço de byte da CPU. |
| Absoluto | `addr // 4` | Qualquer coisa que raciocine sobre a visão da memória por endereço de byte da própria CPU. |

## Configuração

| Chave | Significado |
| :--- | :--- |
| `quartus.ram_mem_instance` | Índice da instância do tap de debug da RAM (padrão `1`). |
| `quartus.poll_interval_seconds` | De quanto em quanto tempo reler o `tohost` enquanto espera um resultado (padrão `0.5`). |
| `memory.ram_base` | Endereço de byte base da RAM. Sem padrão; específico do projeto. |
| `memory.tohost_addr` | Endereço de byte do `tohost` (8 bytes). Sem padrão; específico do projeto. |
| `memory.fromhost_addr` | Endereço de byte do `fromhost` (8 bytes). Sem padrão; específico do projeto. |

## Pré-requisitos

- O Quartus Prime Lite no `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), instalado como no `QUARTUS_INSTALL.md` do Infra, e uma placa com um USB-Blaster conectado por JTAG, com as instâncias do In-System Memory Content Editor que o design do projeto expõe.

## Testes

Não há teste automatizado neste repositório. Um runner self-hosted preparado como no `RUNNER_SETUP.md` do Infra roda a suíte de hardware real de um projeto consumidor (`riscv-tools run`), que é o único lugar onde este módulo é exercitado.

## Uso

```bash
uv run riscv-tools --config /path/to/project/config.yaml htif read
uv run riscv-tools --config /path/to/project/config.yaml htif restart
uv run riscv-tools --config /path/to/project/config.yaml generate-header
```

`read` imprime `TOHOST=<valor>` e `restart` escreve no `fromhost`; servem mais para depuração manual; o [`orchestrator`](orchestrator.md) chama as mesmas funções direto no próprio laço por teste.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
