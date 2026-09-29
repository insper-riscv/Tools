# `spike_exec`

Prepara e dispara execuções do Spike. É a etapa compartilhada por trás do [`golden_generator`](golden_generator.md) e do [`spike_run`](spike_run.md): nenhum dos dois monta por conta própria uma linha de comando do Spike nem mexe num ELF.

## O que faz

| Etapa | Comportamento |
| :--- | :--- |
| Preflight | Procura `emulator.spike_bin` no `PATH` (ou como caminho) e o sonda uma vez por processo. Um Spike que coloca o módulo de debug no endereço 0 aborta com `devices at [0, 1000) and [0, 10000) overlap` sempre que a ROM do alvo começa no endereço 0, então é rejeitado com uma indicação do `SPIKE_SETUP.md` do Infra. |
| Preparação do ELF | Copia o ELF para um diretório temporário e, com `objcopy --add-symbol`, define o que o Spike precisa: `fromhost` logo depois de `tohost` quando o link script não o define (sem os dois, o Spike avisa e nunca termina ao concluir), um alias `tohost` quando `emulator.tohost_symbol` usa outro nome, e quaisquer símbolos extras que quem chama pedir (como `begin_signature`). O ELF original nunca é modificado. |
| Linha de comando | `--isa`, um `-m` por região de memória real, `--disable-dtb` e `--pc`. A memória padrão do próprio Spike fica em `0x80000000` e o vetor de reset dele passa por uma boot ROM em `0x1000`, e os dois colidem com um alvo cuja memória começa perto do endereço 0. |

## Configuração

| Chave | Significado |
| :--- | :--- |
| `emulator.spike_bin` | Nome ou caminho do binário `spike` (padrão `spike`). |
| `emulator.tohost_symbol` | Símbolo em que o programa escreve ao terminar (padrão `tohost`). |
| `toolchain.nm`, `toolchain.objcopy` | Resolvem endereços de símbolos e acrescentam símbolos à cópia do ELF. |

## Pré-requisitos

- O `spike` no `PATH`, instalado como no `SPIKE_SETUP.md` do [insper-riscv/Infra](https://github.com/insper-riscv/Infra) (o build mantém o módulo de debug do Spike longe do endereço 0).
- A toolchain GCC RISC-V (`riscv32-unknown-elf-nm` e `-objcopy`) no `PATH`, instalada como no `GCC_SETUP.md` do Infra.

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_spike_exec.py::test_require_spike_missing_binary_points_at_setup_doc` | Um Spike ausente levanta um erro que aponta o `SPIKE_SETUP.md`. |
| `tests/test_spike_exec.py::test_require_spike_rejects_debug_module_at_address_zero` | Um Spike cujo módulo de debug se sobrepõe a uma ROM no endereço 0 é rejeitado. |
| `tests/test_spike_exec.py::test_require_spike_accepts_a_binary_without_the_overlap` | Um Spike sem a sobreposição é aceito. |
| `tests/test_spike_exec.py::test_spike_command_lists_every_region_and_the_entry_point` | A linha de comando carrega todas as regiões de memória, o ponto de entrada e os argumentos extras. |
| `tests/test_spike_exec.py::test_prepared_elf_adds_fromhost_and_extra_symbols` | `fromhost` e os símbolos pedidos são acrescentados a uma cópia temporária, e o original não é alterado. |
| `tests/test_spike_exec.py::test_prepared_elf_aliases_a_custom_tohost_symbol` | O nome próprio de `tohost` de um projeto ganha um alias `tohost`. |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
