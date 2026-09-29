# `ram_zero`

Zera todas as palavras de uma instância de RAM por JTAG, sem reprogramar a placa. Internamente só escreve um `.mif` de profundidade completa todo em zero pelo [`mem_edit.write_full`](mem_edit.md): "zerar" é "escrever este conteúdo específico", e não uma primitiva dedicada de zeragem do lado do Quartus.

## Configuração

| Chave | Significado |
| :--- | :--- |
| `quartus.ram_mem_instance` | Índice de instância que o In-System Memory Content Editor do Quartus atribui ao tap de debug da RAM. `1` é o caso comum (RAM instanciada logo depois da ROM). |
| `memory.ram_words` | Profundidade da RAM em palavras, específica do projeto. |

## Pré-requisitos

- O Quartus Prime Lite no `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), instalado como no `QUARTUS_INSTALL.md` do Infra, e uma placa com um USB-Blaster conectado por JTAG, com a instância de RAM que o design do projeto expõe.

## Testes

Não há teste automatizado neste repositório. Um runner self-hosted preparado como no `RUNNER_SETUP.md` do Infra roda a suíte de hardware real de um projeto consumidor (`riscv-tools run`), que é o único lugar onde este módulo é exercitado.

## Uso

```bash
uv run riscv-tools --config /path/to/project/config.yaml zero-ram
```

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
