# `compiler`

Compila um fonte de teste bare-metal (`.c` ou `.S`) num `.elf`/`.bin` linkado. É o que o `compile --emit mif|hex|asm` (veja Uso abaixo) chama uma vez por teste descoberto no `c_dir`/`asm_dir` de um projeto.

## Convenções de cabeçalho por teste

O fonte de cada teste declara os requisitos de build/execução em comentários no topo, lidos por este módulo:

| Cabeçalho | Significado |
| :--- | :--- |
| `// RV32_EXT: M` | Compilado com `-march=rv32im` (as letras de extensão se somam à base `rv32i` implícita; separadas por vírgula, a ordem não importa, normalizadas por `isa.canonical_order`). Omitido por completo significa `rv32i` puro. |
| `// RV32_TEST_KIND: unit` | Padrão se omitido. Verificado só pelo mailbox PASS/FAIL (veja [`mailbox`](mailbox.md)). |
| `// RV32_TEST_KIND: memory` | Também faz o dump da RAM e a compara com um golden JSON (veja [`mem_validator`](mem_validator.md), [`golden_generator`](golden_generator.md)). |
| `// RV32_TIMEOUT_S: 5` | Quanto o [`orchestrator`](orchestrator.md) espera o mailbox deste teste antes de recorrer a uma reprogramação completa. O padrão é o `default_timeout_s` do `orchestrator`. |

## Biblioteca C

`toolchain.libc` seleciona com o que um teste linka:

| Valor | Flags | Uso |
| :--- | :--- | :--- |
| `none` (padrão) | `-nostdlib` | Funciona com qualquer toolchain. Um teste que precisa de `malloc` ou algo parecido o obtém do `paths.syscalls` do próprio projeto. |
| `picolibc` | `--specs=picolibc.specs -Wl,--no-gc-sections` | Para um GCC configurado com picolibc, como o que o `GCC_SETUP.md` do Infra compila para `rv32im`/`ilp32`. `strlen`, `memcpy`, `printf` e o resto vêm da picolibc. |

O código de startup continua sendo o `crt0.S` do próprio projeto (`-nostartfiles` nos dois casos). O `picolibc.specs` liga o `--gc-sections`, que descarta toda seção que um link script não mantém nem alcança a partir da entrada, então ele é desligado de novo. Essa toolchain tem uma única variante de biblioteca (`rv32im`/`ilp32`), então um teste compilado para um `-march` mais estreito linka código de biblioteca que pode usar instruções que o seu núcleo não tem, como multiplicação e divisão no `printf`.

## Formato do arquivo hex

Com `sim.hex_format: verilog`, o `.hex` de simulação vem direto do ELF linkado, por `objcopy -O verilog --verilog-data-width=4`, em vez de vir do binário plano. O arquivo mantém os endereços de palavra reais da imagem:

```
@00000200
00100293 00200313 FF9FF06F
@00000203
DEADBEEF
```

Um programa linkado em `0x800` começa em `@00000200` (endereço de palavra), então não precisa de palavras zero à esquerda, e uma lacuna entre seções vira uma nova linha `@`. O formato padrão `words` mantém uma palavra de 32 bits por linha.

## Configuração

| Chave | Significado |
| :--- | :--- |
| `toolchain.gcc` | Nome/caminho do binário do GCC (padrão `riscv32-unknown-elf-gcc`). |
| `toolchain.objcopy` | Nome/caminho do binário do objcopy (padrão `riscv32-unknown-elf-objcopy`). |
| `toolchain.libc` | `none` ou `picolibc` (padrão `none`); veja [Biblioteca C](#biblioteca-c). |
| `isa.base` | Letra da ISA base, sempre `i`, nunca escrita no cabeçalho do próprio teste. |
| `isa.default_ext` | String de extensões usada quando um teste não tem o cabeçalho `RV32_EXT`. Vazia por padrão (`rv32i` puro). |
| `isa.canonical_order` | Ordem fixa de letras em que as extensões são ordenadas antes de serem acrescentadas à string da ISA base, de modo que `RV32_EXT: A,M` e `RV32_EXT: M,A` normalizam para o mesmo valor de `-march=`. |
| `paths.include_dir`, `paths.crt0`, `paths.linker_script`, `paths.build_dir`, `paths.c_dir`, `paths.asm_dir` | Todos são caminhos específicos do projeto, dentro do repositório consumidor; sem padrão, todo projeto precisa defini-los. |

## Pré-requisitos

- A toolchain GCC RISC-V (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) no `PATH`, instalada como no `GCC_SETUP.md` do [insper-riscv/Infra](https://github.com/insper-riscv/Infra).

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_compiler_headers.py::test_canonical_march_no_ext` | Um teste sem cabeçalho de extensão resolve para a ISA base. |
| `tests/test_compiler_headers.py::test_canonical_march_single_ext` | Uma letra de extensão é acrescentada à base. |
| `tests/test_compiler_headers.py::test_canonical_march_order_independent` | As letras de extensão são ordenadas na ordem canônica. |
| `tests/test_compiler_headers.py::test_parse_header_defaults` | Cabeçalhos ausentes voltam aos padrões. |
| `tests/test_compiler_headers.py::test_parse_header_all_fields` | `RV32_EXT`, `RV32_TEST_KIND` e `RV32_TIMEOUT_S` são todos lidos. |
| `tests/test_cli_compile.py::test_discover_tests_finds_c_and_asm_sorted_by_name` | Testes em C e assembly são encontrados e ordenados por nome. |
| `tests/test_cli_compile.py::test_discover_tests_empty_when_no_folders` | Nenhuma pasta de testes resulta em nenhum teste. |
| `tests/test_cli_compile.py::test_cmd_compile_mif_builds_every_kind` | Um teste C, um teste C de memória e um teste assembly compilam e entram no manifest. |
| `tests/test_cli_compile.py::test_cmd_compile_hex_builds_every_kind` | Os mesmos testes compilam para simulação. |
| `tests/test_cli_compile.py::test_cmd_compile_hex_uses_the_verilog_format_when_configured` | `sim.hex_format: verilog` escreve o layout do `objcopy`. |
| `tests/test_compiler_hex.py::test_elf_to_verilog_hex_keeps_the_real_word_address` | Uma imagem linkada em `0x800` começa em `@00000200`, sem preenchimento de zeros. |
| `tests/test_compiler_libc.py::test_libc_flags_defaults_to_no_libc` | Sem `toolchain.libc`, os testes linkam com `-nostdlib`. |
| `tests/test_compiler_libc.py::test_libc_flags_picolibc_keeps_sections_the_link_script_does_not_reach` | `picolibc` seleciona as specs e desliga a coleta de lixo de seções. |
| `tests/test_compiler_libc.py::test_libc_flags_rejects_an_unknown_library` | Um valor desconhecido levanta um erro que cita a chave. |
| `tests/test_compiler_libc.py::test_picolibc_provides_libc_functions` | Um teste que chama `strlen` linka com `picolibc` (pulado sem um GCC configurado com picolibc). |
| `tests/test_compiler_libc.py::test_no_libc_leaves_libc_functions_undefined` | O mesmo teste falha no link com `none` (pulado sem um GCC configurado com picolibc). |

## Uso

Não é um subcomando próprio da CLI: é o que o `compile` (veja o [README](../../../README.md#uso) principal) roda uma vez por teste descoberto, antes de passar o resultado para o [`bin_to_image`](bin_to_image.md) (para `.mif`/`.hex`), o [`c_to_asm`](c_to_asm.md) (para inspeção de `.S`) ou o [`golden_generator`](golden_generator.md) (para o golden gerado automaticamente de um teste C do tipo `memory`).

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
