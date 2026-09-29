# `certify`

Compila e roda a suíte ACT4 (RISC-V Architectural Certification Tests) sob cocotb/GHDL, validando contra a suíte oficial `riscv-arch-test` em vez dos testes escolhidos a dedo de um projeto. Nunca toca o hardware real: os testes do ACT4 não têm golden JSON próprio e sinalizam a conclusão pelo HTIF `tohost`, e não pela convenção de mailbox PASS/FAIL de um projeto.

Duas etapas, de responsabilidade de ferramentas diferentes:

1. O `build_elfs` chama o `make` do próprio ACT4 (no `vendor/riscv-arch-test` versionado) para compilar ELFs autoverificáveis do alvo ACT4 do projeto. O ACT4 cuida por inteiro da geração e da compilação dos testes; o projeto consumidor só fornece a configuração específica do DUT (YAML do alvo, YAML do UDB, header de macros, linker script).
2. O `run_suite` converte cada ELF compilado do mesmo jeito que o [`compiler`](compiler.md) converte os testes do próprio projeto (`objcopy` para `.bin` cru, depois [`bin_to_image`](bin_to_image.md) para `.hex`), e então o passa pelo mesmo toplevel cocotb/GHDL que o [`sim_runner`](sim_runner.md) usa na suíte normal, reaproveitando direto do `config.yaml` o `sim.vhdl_sources`/`sim.toplevel`/`sim.ghdl_std`. Só o `test_module` muda, já que os testes do ACT4 sinalizam a conclusão por HTIF, e não pela convenção de mailbox do próprio projeto.

Precisa de um GCC RISC-V no `PATH` para o build do próprio ACT4 (o `compile_exe` do `test_config.yaml` do alvo ACT4) e do `toolchain.objcopy` para a segunda etapa. Nenhum Spike é envolvido.

## Configuração

| Chave | Significado |
| :--- | :--- |
| `act.vendor_dir` | Caminho do próprio framework ACT4 versionado (padrão `vendor/riscv-arch-test`). |
| `act.target_config` | O arquivo de configuração do alvo ACT4 do próprio projeto. Sem padrão. |
| `act.extensions` | Lista de extensões separadas por vírgula repassada ao `make ... EXTENSIONS=` do próprio ACT4 (padrão `"I,M"`). |
| `act.jobs` | O paralelismo do próprio `make` (padrão `0`, a detecção automática do próprio ACT4). |
| `act.sim_parameters` | Mesclado por cima de `sim.parameters`; só necessário para sobrescrever algo que as imagens maiores do ACT4 dimensionam diferente do orçamento de hardware real do projeto (por exemplo `rom_addr_width`/`ram_addr_width`). Vazio por padrão. |

## Pré-requisitos

- A toolchain GCC RISC-V (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) no `PATH`, instalada como no `GCC_SETUP.md` do [insper-riscv/Infra](https://github.com/insper-riscv/Infra), para o build do próprio ACT4.
- O extra `sim` (`uv sync --extra sim`) e o GHDL no `PATH`.
- A toolchain Ruby, Bundler e UDB do ACT4, e o checkout do ACT4 para o qual a chave `act.vendor_dir` aponta.

## Testes

Não há teste automatizado neste repositório. O workflow de certificação de um projeto consumidor o executa.

## Uso

```bash
uv sync --extra sim
uv run riscv-tools --config /path/to/project/config.yaml certify
```

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
