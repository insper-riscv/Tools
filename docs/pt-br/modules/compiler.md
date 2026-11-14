# `compiler`

Compila um fonte de teste bare-metal (`.c`, `.cc`, `.cpp` ou `.S`) num `.elf`/`.bin` linkado. É o que o `compile --emit mif|hex|asm` (veja Uso abaixo) chama uma vez por teste descoberto no `c_dir`/`asm_dir` de um projeto.

## Convenções de cabeçalho por teste

O fonte de cada teste declara os requisitos de build/execução em comentários no topo, lidos por este módulo:

| Cabeçalho | Significado |
| :--- | :--- |
| `// RV32_EXT: M` | Compilado com `-march=rv32im` (as letras de extensão se somam à base `rv32i` implícita; separadas por vírgula, a ordem não importa, normalizadas por `isa.canonical_order`). Omitido por completo significa `rv32i` puro. |
| `// RV32_TEST_KIND: unit` | Padrão se omitido. Verificado só pelo `tohost` (veja [`htif`](htif.md)). |
| `// RV32_TEST_KIND: memory` | Também faz o dump da RAM e a compara com um golden JSON (veja [`mem_validator`](mem_validator.md), [`golden_generator`](golden_generator.md)). |
| `// RV32_TIMEOUT_S: 5` | Quanto o [`orchestrator`](orchestrator.md) espera o `tohost` deste teste antes de recorrer a uma reprogramação completa. O padrão é o `default_timeout_s` do `orchestrator`. |

## Biblioteca C

`toolchain.libc` seleciona com o que um teste linka:

| Valor | Flags | Uso |
| :--- | :--- | :--- |
| `none` (padrão) | `-nostdlib` | Funciona com qualquer toolchain. Um teste que precisa de `malloc` ou algo parecido o obtém do `paths.syscalls` do próprio projeto. |
| `picolibc` | `--specs=picolibc.specs -Wl,--no-gc-sections` | Para um GCC configurado com picolibc, como o que o `manual/GCC_SETUP.md` do Infra compila para `rv32im`/`ilp32`. `strlen`, `memcpy`, `printf` e o resto vêm da picolibc. |

O código de startup continua sendo o `crt0.S` do próprio projeto (`-nostartfiles` nos dois casos). O `picolibc.specs` liga o `--gc-sections`, que descarta toda seção que um link script não mantém nem alcança a partir da entrada, então ele é desligado de novo. Essa toolchain tem uma única variante de biblioteca (`rv32im`/`ilp32`), então um teste compilado para um `-march` mais estreito linka código de biblioteca que pode usar instruções que o seu núcleo não tem, como multiplicação e divisão no `printf`.

## C++

`toolchain.cxx: true` (padrão `false`) deixa um teste ser escrito em C++, no `src.cc` ou no `src.cpp` da pasta dele em `c_dir`. Ele exige `toolchain.libc: picolibc` ou um `toolchain.specs`, e uma toolchain construída com a `libstdc++` da variante do teste.

| Peça | O que muda com `cxx: true` num teste `.cc` ou `.cpp` |
| :--- | :--- |
| Driver | O `g++` da toolchain: o nome do `gcc` com `g++` no lugar, ou `toolchain.gxx`. Ele liga `-lstdc++` e `-lm` sozinho |
| Norma | ISO/IEC 14882:2024 (C++23), `-std=c++23 -Wall -Wextra -Wpedantic -Werror` |
| Flags extras | `toolchain.cxx_options`, uma lista só para fontes C++, como `["-fno-exceptions", "-fno-rtti"]` |
| Specs, sem `toolchain.specs` | `--specs=picolibcpp.specs --crt0=hosted`, que liga `crtbegin.o` e `crtend.o` e faz o `main` que retorna chamar `exit`, e o linker script `picolibcpp.ld` (`-T`, salvo `paths.linker_script`) |
| Specs, com `toolchain.specs` | O arquivo gerado com `cxx: true` (ver [`memory_map`](memory_map.md)), que já traz tudo isso |
| Fontes C do projeto | Os de `paths.sources` são compilados à parte, como C, e ligados ao teste; as flags só de C++ de `emulator.gcc_flags` ficam fora desse compile |

O `crtbegin.o` registra os quadros de desenrolamento, e o `crtend.o` termina o `.eh_frame`. O `picolibc.specs` deixa os dois de fora, e sem eles um `throw` salta para o endereço 0 ou lê lixo no fim da tabela. Por isso o `crt0` do projeto (`paths.crt0`) não vale com C++, e o compile recusa essa combinação.

O `picolibc.specs` e um arquivo de specs que já o inclui não convivem na mesma linha de comando. O driver para com `attempt to rename spec 'link' to already defined spec 'picolibc_link'`, então um teste recebe um só dos dois, e o `toolchain.specs` do projeto já inclui o `picolibc.specs`.

Antes de compilar, o compile confere se a toolchain tem a `libstdc++.a` da variante (`-march` e `-mabi` do teste). Sem ela o teste falha com a mensagem `toolchain.cxx is true but the toolchain has no libstdc++.a for the variant -march=... -mabi=...: the toolchain must be built with libstdc++ for it`, e não com `cannot find -lstdc++` na ligação nem com `bits/c++config.h` ausente na compilação.

A `libstdc++` pede ao runtime `getentropy`, `read`, `open` e `close` (pelo `std::random_device`, que todo programa com `new` ou exceção carrega) e as streams `stdout` e `stderr` (pelo tratador de `std::terminate`). As quatro funções saem prontas do `generate.syscalls` do [`memory_map`](memory_map.md), e as streams são as do `stdio.c` da plataforma.

Os atômicos ficam fora do escopo. O GCC não constrói a `libatomic` para `riscv32-unknown-elf`, então um `std::atomic` de 8 bytes, e qualquer `std::atomic` numa variante sem a extensão A, fica com `__atomic_*` sem definição na ligação.

## Norma C23

Todo fonte C compilado por este pacote segue a ISO/IEC 9899:2024 (C23). O compile de um teste, o `c_to_asm`, a memória de boot e o programador de NOR passam ao GCC `-std=c23` (e não `-std=gnu23`) e `-Wall -Wextra -Wpedantic -Werror`, de modo que qualquer aviso interrompe o build. As flags ficam na constante `C_STANDARD_FLAGS`, já incluída em `optimize_flags`. O `rv32_test.h` gerado declara `rv32_wait_restart` com o atributo padrão `[[noreturn]]`, e não com `__attribute__`.

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

Quando a imagem de um programa termina em código que, no hardware, fica em outro lugar, o Spike não consegue executá-la como está. `emulator.sources` e `emulator.gcc_flags` montam um segundo ELF para o Spike, a partir das mesmas fontes mais um substituto: no exemplo acima, o `rv32_wait_restart` do hardware é uma rotina da memória de boot no endereço `0x100`, e o ELF do Spike é compilado com `-DRV32_SPIKE`, que tira esse endereço fixo do link, e com um arquivo que define o `rv32_wait_restart` como código comum (ela só espera, pois o teste já escreveu o `tohost`) e os símbolos `tohost` e `fromhost`. Sem `emulator.sources`, o Spike executa a imagem do próprio teste.

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
| `toolchain.cxx` | `true` liga o C++ (padrão `false`); veja [C++](#c). |
| `toolchain.gxx` | Nome ou caminho do `g++`; o padrão é o `gcc` com `g++` no lugar. |
| `toolchain.cxx_options` | Lista de flags só para fontes C++ (padrão vazia). |
| `toolchain.specs` | Caminho opcional do arquivo de especificação da plataforma; com ele, `paths.crt0` e `paths.linker_script` não são necessários (veja Arquivo de especificação da plataforma). |
| `paths.sources` | Lista opcional de arquivos-fonte compilados em todo teste (o `_exit` da plataforma, por exemplo). |
| `isa.base` | Letra da ISA base, sempre `i`, nunca escrita no cabeçalho do próprio teste. |
| `isa.default_ext` | String de extensões usada quando um teste não tem o cabeçalho `RV32_EXT`. Vazia por padrão (`rv32i` puro). |
| `isa.canonical_order` | Ordem fixa de letras em que as extensões são ordenadas antes de serem acrescentadas à string da ISA base, de modo que `RV32_EXT: A,M` e `RV32_EXT: M,A` normalizam para o mesmo valor de `-march=`. |
| `paths.include_dir`, `paths.crt0`, `paths.linker_script`, `paths.build_dir`, `paths.c_dir`, `paths.asm_dir` | Todos são caminhos específicos do projeto, dentro do repositório consumidor; sem padrão, todo projeto precisa defini-los. |

## Pré-requisitos

- A toolchain GCC RISC-V (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) no `PATH`, que a imagem `ci-elf` do [insper-riscv/Infra](https://github.com/insper-riscv/Infra) já traz, ou instalada como no `manual/GCC_SETUP.md` dele.

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
| `tests/test_cli_compile.py::test_cmd_compile_only_builds_just_the_named_tests` | `--only` compila só os testes nomeados e o manifest lista apenas eles. |
| `tests/test_cli_compile.py::test_cmd_compile_only_rejects_an_unknown_test` | `--only` com um nome inexistente termina com erro. |
| `tests/test_cli_compile.py::test_cmd_compile_hex_builds_every_kind` | Os mesmos testes compilam para simulação. |
| `tests/test_cli_compile.py::test_cmd_compile_hex_uses_the_verilog_format_when_configured` | `sim.hex_format: verilog` escreve o layout do `objcopy`. |
| `tests/test_compiler_hex.py::test_elf_to_verilog_hex_keeps_the_real_word_address` | Uma imagem linkada em `0x800` começa em `@00000200`, sem preenchimento de zeros. |
| `tests/test_compiler_libc.py::test_libc_flags_defaults_to_no_libc` | Sem `toolchain.libc`, os testes linkam com `-nostdlib`. |
| `tests/test_compiler_libc.py::test_libc_flags_picolibc_keeps_sections_the_link_script_does_not_reach` | `picolibc` seleciona as specs e desliga a coleta de lixo de seções. |
| `tests/test_compiler_libc.py::test_libc_flags_rejects_an_unknown_library` | Um valor desconhecido levanta um erro que cita a chave. |
| `tests/test_compiler_libc.py::test_picolibc_provides_libc_functions` | Um teste que chama `strlen` linka com `picolibc` (pulado sem um GCC configurado com picolibc). |
| `tests/test_compiler_libc.py::test_no_libc_leaves_libc_functions_undefined` | O mesmo teste falha no link com `none` (pulado sem um GCC configurado com picolibc). |
| `tests/test_platform_runtime.py::test_compile_needs_no_crt0_or_linker_script` | Com um arquivo de especificação, um teste compila e linka sem `crt0` e sem linker script: o `_start` fica na base da flash e a rotina da memória de boot no endereço fixo dela. |
| `tests/test_platform_runtime.py::test_cmd_compile_builds_every_kind_and_the_goldens` | Um teste C, um teste C de memória, um que retorna de `main`, um com dados inicializados e um em assembly compilam; o Spike gera o golden a partir da imagem montada com o substituto. |
| `tests/test_platform_runtime.py::test_cmd_spike_run_passes_programs_that_return_from_main` | Os mesmos testes passam no Spike, inclusive os que retornam de `main` e o que confere `.data`, `.bss` e uma constante. |
| `tests/test_platform_runtime.py::test_cmd_compile_hex_places_the_image_at_the_flash_base` | A imagem de simulação começa na base da flash. |
| `tests/test_compiler_cxx.py::test_cxx_with_picolibc_is_on` | `cxx: true` com picolibc ou com um arquivo de specs liga o C++; sem picolibc, ou com um valor que não é booleano, é recusado. |
| `tests/test_compiler_cxx.py::test_the_gxx_is_the_gcc_with_the_name_changed` | O `g++` sai do nome do `gcc`, ou de `toolchain.gxx`. |
| `tests/test_compiler_cxx.py::test_cxx_flags_use_the_cpp_specs_and_linker_script` | As flags trazem o `picolibcpp.specs` e o `picolibcpp.ld`, salvo linker script do projeto. |
| `tests/test_compiler_cxx.py::test_the_library_of_another_variant_is_refused` | A `libstdc++.a` da variante padrão que o driver devolve para outra variante não vale. |
| `tests/test_compiler_cxx.py::test_a_variant_without_the_library_is_refused_by_name` | A recusa diz a variante e que a toolchain precisa da `libstdc++`. |
| `tests/test_compiler_cxx.py::test_a_cxx_source_refuses_a_project_crt0` | `paths.crt0` com C++ é recusado antes de qualquer compilador. |
| `tests/test_compiler_cxx.py::test_c_extras_drop_the_flags_only_cpp_takes` | As fontes C de um teste C++ são compiladas sem as flags só de C++. |
| `tests/test_compiler_cxx.py::test_discovery_finds_cc_and_cpp_tests` | Uma pasta com `src.cc` ou `src.cpp` é um teste. |
| `tests/test_cxx_generate.py::test_cxx_specs_register_the_unwind_frames` | O arquivo de specs com `cxx: true` liga `crtbegin` e `crtend` e escolhe o `crt0` direto. |
| `tests/test_cxx_generate.py::test_cxx_false_is_the_c_specs_file` | Com `cxx` falso, o arquivo de specs é idêntico ao de C. |
| `tests/test_cxx_generate.py::test_syscalls_are_the_stubs_the_libstdcxx_needs` | `generate.syscalls` escreve `getentropy`, `read`, `open` e `close`, cada uma com `ENOSYS`. |
| `tests/test_cxx_generate.py::test_syscalls_are_for_cxx_only` | `generate.syscalls` sem `cxx: true` em algum arquivo de specs é recusado. |
| `tests/test_cxx_runtime.py::test_cxx_programs_run` | Construtor global, virtual com `new` e `delete`, `std::array` e `std::vector` passam no Spike em `rv32i` e `rv32im` (pulado sem uma toolchain com `libstdc++`). |
| `tests/test_cxx_runtime.py::test_throw_and_catch_run_the_destructors` | Um `throw` é capturado e destrói os locais, pelos quadros que o `crtbegin` registra. |
| `tests/test_cxx_runtime.py::test_no_exceptions_no_rtti_runs` | `-fno-exceptions -fno-rtti` ainda liga e roda. |

## Uso

Não é um subcomando próprio da CLI: é o que o `compile` (veja o [README](../../../README.md#uso) principal) roda uma vez por teste descoberto, antes de passar o resultado para o [`bin_to_image`](bin_to_image.md) (para `.mif`/`.hex`), o [`c_to_asm`](c_to_asm.md) (para inspeção de `.S`) ou o [`golden_generator`](golden_generator.md) (para o golden gerado automaticamente de um teste C do tipo `memory`).

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
