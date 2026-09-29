# `spike_run`

Roda o ELF de um teste compilado até o fim no Spike e reporta PASS ou FAIL, sem hardware e sem simulador. É uma checagem de software rápida para rodar antes de uma suíte de hardware real ou de simulação: o `riscv-tools spike-run` lê o manifest que o `compile --emit mif` escreveu e roda todos os testes dele.

## Como o veredito é lido

O `crt0.S` do teste escreve `1` no HTIF `tohost` para um pass e `3` para um fail. O Spike termina com esse valor deslocado um bit para a direita, então:

| `tohost` | Status de saída do Spike | Resultado |
| :--- | :--- | :--- |
| `1` | `0` | PASS |
| `3` | `1` | FAIL |
| nunca escrito | (morto no timeout) | FAIL, reportado como estouro de tempo |

## Configuração

| Chave | Significado |
| :--- | :--- |
| `emulator.spike_bin` | Nome ou caminho do binário `spike` (padrão `spike`); veja o [golden_generator](golden_generator.md) para os requisitos dele. |
| `emulator.tohost_symbol` | Símbolo em que o teste escreve o veredito (padrão `tohost`). |
| `emulator.entry_symbol` | Símbolo em que a execução começa (padrão `_start`). |
| `emulator.timeout_s` | Segundos de espera quando um teste não tem o cabeçalho `RV32_TIMEOUT_S` (padrão `60`). O `RV32_TIMEOUT_S` do próprio teste tem precedência. |
| `toolchain.nm`, `toolchain.objcopy` | Resolvem os símbolos de entrada e de `tohost` e acrescentam `fromhost` a uma cópia temporária do ELF quando o link script não o define. |
| `memory.*` | As regiões de ROM e RAM entregues ao `-m` do Spike, as mesmas que o [golden_generator](golden_generator.md) usa. |

Um projeto com boot ROM separada (`paths.golden_linker_script` e `paths.boot_rom`) roda pelo mesmo ELF autocontido que o gerador de goldens compila, já que a imagem só de FLASH não tem ponto de entrada de onde o Spike consiga partir.

## Pré-requisitos

- O `spike` no `PATH`, instalado como no `SPIKE_SETUP.md` do [insper-riscv/Infra](https://github.com/insper-riscv/Infra) (o build mantém o módulo de debug do Spike longe do endereço 0).
- A toolchain GCC RISC-V (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) no `PATH`, instalada como no `GCC_SETUP.md` do [insper-riscv/Infra](https://github.com/insper-riscv/Infra) (`nm` e `objcopy`; o `gcc` compila as fixtures).

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_spike_run.py::test_run_elf_reports_pass_when_tohost_is_1` | `tohost = 1` é um pass com status de saída 0. |
| `tests/test_spike_run.py::test_run_elf_reports_fail_when_tohost_is_3` | `tohost = 3` é um fail com status de saída 1. |
| `tests/test_spike_run.py::test_run_elf_times_out_when_tohost_is_never_written` | Um teste que nunca escreve `tohost` é reportado como estouro de tempo. |
| `tests/test_cli_compile.py::test_cmd_spike_run_passes_compiled_tests` | O `spike-run` reporta PASS para testes compilados a partir de um manifest. |
| `tests/test_cli_compile.py::test_cmd_spike_run_rejects_a_test_missing_from_the_manifest` | `--only` com um nome desconhecido termina com erro. |

## Uso

```bash
uv run riscv-tools --config /path/to/project/config.yaml compile --emit mif
uv run riscv-tools --config /path/to/project/config.yaml spike-run
uv run riscv-tools --config /path/to/project/config.yaml spike-run --only add,mem
```

O status de saída é `1` quando algum teste falha, o que o torna utilizável como portão de CI. A saída completa também é escrita em `<run_log.logs_dir>/spike/latest.log`.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
