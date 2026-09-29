# `boot_rom`

Compila o bootloader fixo e compartilhado (o `boot_rom.S`/`boot_rom.ld` do próprio projeto) num binário plano e o converte em `.hex`. É compilado uma vez por execução, e não uma vez por teste: a BOOT_ROM não tem fonte de teste, nem par com `crt0`, e não faz parte do manifest de nenhum teste. Todo consumidor que precisa da imagem dela ([`sim_runner`](sim_runner.md) para o GHDL, [`rom_writer`](rom_writer.md)/[`orchestrator`](orchestrator.md) para o hardware real) chama `build_boot_rom` uma vez e reaproveita o resultado, do mesmo jeito que a imagem compilada de um teste é reaproveitada no laço de testes de um manifest em vez de ser recompilada a cada teste.

## Configuração

Usa as mesmas configurações `toolchain.gcc`/`toolchain.objcopy` do [`compiler`](compiler.md), mais o `paths.boot_rom`/`paths.boot_rom_linker_script` do próprio projeto (específicos do projeto, sem padrão).

## Pré-requisitos

- A toolchain GCC RISC-V (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) no `PATH`, instalada como no `GCC_SETUP.md` do [insper-riscv/Infra](https://github.com/insper-riscv/Infra).

## Testes

Não há teste automatizado neste repositório. As suítes de hardware real e de simulação de um projeto consumidor compilam a boot ROM dele (`riscv-tools program`, `riscv-tools sim`), e o workflow `sim` dele a roda a cada push.

## Uso

Não é um subcomando próprio da CLI: é chamado uma vez no início de uma execução em hardware real (antes do `quartus_sh`/`quartus_pgm` inicial, veja [`quartus_program`](quartus_program.md)) ou de uma execução de simulação (veja [`sim_runner`](sim_runner.md)), nunca por teste.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
