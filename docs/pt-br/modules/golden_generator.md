# `golden_generator`

Gera um golden JSON dinamicamente rodando o ELF de um teste compilado no Spike (o simulador de referência da RISC-V International) até ele sinalizar a conclusão pelo HTIF `tohost`, e então lendo o intervalo de memória pedido do arquivo de assinatura que o Spike escreve, em vez de uma pessoa calcular à mão os valores de memória esperados. Mecanismo completo e requisitos: [docs/generating-a-golden.md](../generating-a-golden.md).

## Configuração

| Chave | Significado |
| :--- | :--- |
| `toolchain.nm` | Binário `nm` usado para resolver o endereço de um símbolo no ELF compilado (padrão `riscv32-unknown-elf-nm`). |
| `emulator.spike_bin` | Nome ou caminho do binário `spike` (padrão `spike`). Ele precisa manter o módulo de debug longe do endereço 0 (veja [docs/generating-a-golden.md](../generating-a-golden.md#requisitos)); a primeira execução confere isso. |
| `emulator.timeout_s` | Segundos de espera até um teste escrever `tohost`, antes de a geração falhar (padrão `60`). |
| `toolchain.objcopy` | Binário `objcopy` usado para acrescentar os símbolos de que o Spike precisa a uma cópia do ELF (compartilhado com o [`compiler`](compiler.md)). |
| `emulator.tohost_symbol` | Símbolo HTIF em que um teste escreve um valor diferente de zero ao terminar, e que o Spike observa para saber quando capturar a memória (padrão `tohost`, a convenção padrão do Spike/riscv-tests). |
| `emulator.entry_symbol` | Símbolo em que o Spike começa a execução (padrão `_start`), que pode ser sobrescrito para um projeto cujo ponto de entrada real seja outro, por exemplo o vetor de reset do bootloader compartilhado. |

## Pré-requisitos

- A toolchain GCC RISC-V (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) no `PATH`, que a imagem `ci-elf` do [insper-riscv/Infra](https://github.com/insper-riscv/Infra) já traz, ou instalada como no `manual/GCC_SETUP.md` dele (o `gcc` compila as fixtures; o `nm` e o `objcopy` preparam o ELF).
- O `spike` no `PATH`, que a imagem `ci-elf` do [insper-riscv/Infra](https://github.com/insper-riscv/Infra) já traz, ou instalado como no `manual/SPIKE_SETUP.md` dele (o build mantém o módulo de debug do Spike longe do endereço 0).

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_generate_golden.py::test_generate_golden_reads_back_expected_bytes` | Um teste C e um teste assembly deixam os bytes esperados na captura, em little-endian. |
| `tests/test_generate_golden.py::test_generate_golden_json_round_trips_through_compare` | O golden JSON em disco guarda os mesmos bytes do resultado em memória. |
| `tests/test_generate_golden.py::test_symbol_range_resolves_address_and_size` | Um símbolo com tamanho resolve para o seu endereço e tamanho. |
| `tests/test_generate_golden.py::test_generate_golden_by_symbol_matches_explicit_start_end` | Um intervalo vindo de um símbolo é igual ao mesmo intervalo dado à mão. |
| `tests/test_generate_golden.py::test_generate_golden_rounds_a_partial_word_range_up` | Um intervalo de 1 byte devolve os 4 bytes da sua palavra. |
| `tests/test_golden_words.py::test_group_words_joins_32_bits_little_endian` | `--word-bytes 4` junta 4 bytes numa palavra little-endian. |
| `tests/test_golden_words.py::test_group_words_joins_64_bits_little_endian` | `--word-bytes 8` junta 8 bytes numa palavra little-endian. |
| `tests/test_golden_words.py::test_group_words_rejects_an_incomplete_word` | Uma palavra sem todos os seus bytes é recusada. |
| `tests/test_golden_words.py::test_word_range_rounds_the_end_up` | O fim do intervalo sobe até palavras inteiras. |
| `tests/test_golden_words.py::test_word_range_rejects_an_unaligned_start` | Um início que não é múltiplo do tamanho da palavra é recusado. |
| `tests/test_cli_compile.py::test_cmd_compile_mif_builds_every_kind` | O `compile` gera o golden de um teste C de memória no Spike. |
| `tests/test_cli_compile.py::test_cmd_compile_hex_builds_every_kind` | O mesmo para o build de simulação. |

## Uso

```bash
uv run riscv-tools --config /path/to/project/config.yaml generate-golden \
    build/real/some_test.elf --march rv32im --start 0x10 --end 0x20 --out golden/some_test.json
```

Também é chamado internamente pelo `compile` para todo teste C do tipo `memory` que ainda não tem um `golden.json` versionado, e pelo [`orchestrator`](orchestrator.md) ao rodar de novo uma suíte que precisa de um regenerado.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
