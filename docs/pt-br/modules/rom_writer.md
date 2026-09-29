# `rom_writer`

Carrega uma nova imagem de ROM numa placa já programada por JTAG, sem uma recompilação/reprogramação completa. Faz par com o pulso da "go flag" de reinício do [`mailbox`](mailbox.md) para fazer o núcleo voltar ao ponto de entrada e rodar a imagem recém-escrita (veja o `crt0.S` do próprio projeto consumidor).

Um projeto com mais de uma cópia física do mesmo conteúdo de ROM (veja o `rom_mif_target`/`rom_mem_instances` do [`quartus_program`](quartus_program.md)) escreve em todas as instâncias listadas numa só chamada, mantendo todas as cópias em sincronia.

## Configuração

| Chave | Significado |
| :--- | :--- |
| `quartus.rom_mem_instances` | Índice(s) de instância que o In-System Memory Content Editor do Quartus atribui ao(s) tap(s) de debug da ROM, na ordem de declaração no projeto. `[0]` é o caso comum (uma única ROM instanciada primeiro). |
| `memory.rom_words` | Profundidade da ROM em palavras, específica do projeto. Usada para validar/formatar o `.mif` de um programa antes de escrevê-lo. |

## Pré-requisitos

- O Quartus Prime Lite no `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), instalado como no `QUARTUS_INSTALL.md` do Infra, e uma placa com um USB-Blaster conectado por JTAG, com as instâncias de ROM que o design do projeto expõe.

## Testes

Não há teste automatizado neste repositório. Um runner self-hosted preparado como no `RUNNER_SETUP.md` do Infra roda a suíte de hardware real de um projeto consumidor (`riscv-tools run`), que é o único lugar onde este módulo é exercitado.

## Uso

```bash
uv run riscv-tools --config /path/to/project/config.yaml write-rom <path-to.mif>
```

Também é chamado internamente pelo laço de recarga por JTAG por teste do [`orchestrator`](orchestrator.md), o caminho rápido usado em vez de uma recompilação completa entre testes.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
