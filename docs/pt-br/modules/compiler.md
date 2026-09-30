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

## Arquivo de especificação da plataforma

Com `toolchain.specs`, o projeto não tem `crt0.S` nem linker script. O arquivo de especificação é a descrição inteira da plataforma, e a toolchain faz o resto:

```
%include <picolibc.specs>
%rename link rv32imfpga_picolibc_link

*link:
%(rv32imfpga_picolibc_link) --defsym=__flash=0x800 --defsym=__flash_size=30K --defsym=__ram=0x8000 --defsym=__ram_size=160K-24 %{!DRV32_SPIKE:--defsym=rv32_wait_restart=0x100}

*startfile:
crt0-hosted%O%s
```

| Peça | De onde vem |
| :--- | :--- |
| Linker script | O `picolibc.ld` da toolchain, que o driver do GCC acrescenta quando não vê `-T`; os valores do `--defsym` posicionam a flash e a RAM |
| Startup | O `crt0-hosted` da toolchain: ajusta `sp` e `gp`, copia o `.data` da flash, zera o `.bss`, prepara o TLS, roda os construtores, chama o `main` e chama `exit` com o que o `main` retornou |
| `_exit` | O projeto, por `paths.sources` (a picolibc não o fornece) |

Um teste compilado assim é um programa hospedado: o `-ffreestanding` não é passado, o `main` pode retornar (e assume `return 0`), e o `-nostartfiles` só é passado quando `paths.crt0` indica um arquivo de startup do próprio projeto. `toolchain.libc` é ignorada.

O linker script da toolchain descarta as seções que nada referencia (`--gc-sections`). Um teste C do tipo `memory` é conferido pelo array `results`, que ele pode apenas declarar (um teste que só confere que o `.bss` é zerado nunca o lê), então o compile passa `-Wl,--undefined=results` nesses testes para mantê-lo.

O mesmo arquivo serve a qualquer comando `gcc`, fora deste pacote: `gcc --specs=rv32im-fpga.specs main.c _exit.c`.

### Imagem para o Spike

Quando a imagem de um programa termina em código que, no hardware, fica em outro lugar, o Spike não consegue executá-la como está. `emulator.sources` e `emulator.gcc_flags` montam um segundo ELF para o Spike, a partir das mesmas fontes mais um substituto: no exemplo acima, o `rv32_wait_restart` do hardware é uma rotina da boot ROM no endereço `0x100`, e o ELF do Spike é compilado com `-DRV32_SPIKE`, que tira esse endereço fixo do link, e com um arquivo que define o `rv32_wait_restart` como código comum (o mailbox traduzido para HTIF) e os símbolos `tohost` e `fromhost`. Sem `emulator.sources`, o Spike executa a imagem do próprio teste.

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
| `toolchain.specs` | Caminho opcional do arquivo de especificação da plataforma; com ele, `paths.crt0` e `paths.linker_script` não são necessários (veja Arquivo de especificação da plataforma). |
| `paths.sources` | Lista opcional de arquivos-fonte compilados em todo teste (o `_exit` da plataforma, por exemplo). |
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
| `tests/test_platform_runtime.py::test_compile_needs_no_crt0_or_linker_script` | Com um arquivo de especificação, um teste compila e linka sem `crt0` e sem linker script: o `_start` fica na base da flash e a rotina da boot ROM no endereço fixo dela. |
| `tests/test_platform_runtime.py::test_cmd_compile_builds_every_kind_and_the_goldens` | Um teste C, um teste C de memória, um que retorna de `main`, um com dados inicializados e um em assembly compilam; o Spike gera o golden a partir da imagem montada com o substituto. |
| `tests/test_platform_runtime.py::test_cmd_spike_run_passes_programs_that_return_from_main` | Os mesmos testes passam no Spike, inclusive os que retornam de `main` e o que confere `.data`, `.bss` e uma constante. |
| `tests/test_platform_runtime.py::test_cmd_compile_hex_places_the_image_at_the_flash_base` | A imagem de simulação começa na base da flash. |

## Uso

Não é um subcomando próprio da CLI: é o que o `compile` (veja o [README](../../../README.md#uso) principal) roda uma vez por teste descoberto, antes de passar o resultado para o [`bin_to_image`](bin_to_image.md) (para `.mif`/`.hex`), o [`c_to_asm`](c_to_asm.md) (para inspeção de `.S`) ou o [`golden_generator`](golden_generator.md) (para o golden gerado automaticamente de um teste C do tipo `memory`).

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
