# `ram_dump`

Salva o conteúdo inteiro de uma instância de RAM num `.mif` por JTAG. Usado nos testes `RV32_TEST_KIND: memory`, em que só o mailbox PASS/FAIL não basta para provar que um teste fez a coisa certa (que ele escreveu os valores certos na memória, e não apenas chegou ao próprio sinal de sucesso): veja o [`mem_validator`](mem_validator.md), que compara o dump resultante com um golden JSON.

## Configuração

| Chave | Significado |
| :--- | :--- |
| `quartus.ram_mem_instance` | Índice de instância que o In-System Memory Content Editor do Quartus atribui ao tap de debug da RAM. `1` é o caso comum. |

## Pré-requisitos

- O Quartus Prime Lite no `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), instalado como no `QUARTUS_INSTALL.md` do Infra, e uma placa com um USB-Blaster conectado por JTAG, com a instância de RAM que o design do projeto expõe.

## Testes

Não há teste automatizado neste repositório. Um runner self-hosted preparado como no `RUNNER_SETUP.md` do Infra roda a suíte de hardware real de um projeto consumidor (`riscv-tools run`), que é o único lugar onde este módulo é exercitado.

## Uso

```bash
uv run riscv-tools --config /path/to/project/config.yaml dump-ram <output.mif>
```

Também é chamado internamente pelo [`orchestrator`](orchestrator.md) depois de cada teste do tipo `memory`, antes de passar o dump ao [`mem_validator`](mem_validator.md).

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
