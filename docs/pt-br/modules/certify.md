# `certify`

Compila e roda a suíte ACT4 (RISC-V Architectural Certification Tests) sob cocotb/GHDL, validando contra a suíte oficial `riscv-arch-test` em vez dos testes escolhidos a dedo de um projeto. Nunca toca o hardware real: os testes do ACT4 não têm golden JSON próprio e sinalizam a conclusão pelo HTIF `tohost`, .

Duas etapas, de responsabilidade de ferramentas diferentes:

1. O `build_elfs` chama o `make` do próprio ACT4 (no `vendor/riscv-arch-test` versionado) para compilar ELFs autoverificáveis do alvo ACT4 do projeto. O ACT4 cuida por inteiro da geração e da compilação dos testes; o projeto consumidor só fornece a configuração específica do DUT (YAML do alvo, YAML do UDB, header de macros, linker script).
2. O `run_suite` converte cada ELF compilado do mesmo jeito que o [`compiler`](compiler.md) converte os testes do próprio projeto (`objcopy` para `.bin` cru, depois [`bin_to_image`](bin_to_image.md) para `.hex`), e então o passa pelo mesmo toplevel cocotb/GHDL que o [`sim_runner`](sim_runner.md) usa na suíte normal, reaproveitando direto do `config.yaml` o `sim.vhdl_sources`/`sim.toplevel`/`sim.ghdl_std`. Só o `test_module` muda: é o do ACT4, que lê o `tohost` do jeito que o modelo do ACT4 o escreve.

Precisa de um GCC RISC-V no `PATH` para o build do próprio ACT4 (o `compile_exe` do `test_config.yaml` do alvo ACT4) e do `toolchain.objcopy` para a segunda etapa. Nenhum Spike é envolvido.

## Configuração

| Chave | Significado |
| :--- | :--- |
| `act.vendor_dir` | Caminho do próprio framework ACT4 versionado (padrão `vendor/riscv-arch-test`). |
| `act.target_config` | O arquivo de configuração do alvo ACT4 do próprio projeto. Sem padrão. |
| `act.extensions` | Lista de extensões separadas por vírgula repassada ao `make ... EXTENSIONS=` do próprio ACT4 (padrão `"I,M"`). |
| `act.jobs` | O paralelismo do próprio `make` (padrão `0`, a detecção automática do próprio ACT4). |
| `act.sim_parameters` | Mesclado por cima de `sim.parameters`; só necessário para sobrescrever algo que as imagens maiores do ACT4 dimensionam diferente do orçamento de hardware real do projeto (por exemplo `rom_addr_width`/`ram_addr_width`). Vazio por padrão. |
| `act.flash_base` | Primeiro endereço da FLASH, quando o código do ELF fica nela e os dados na SDRAM (plataforma com a FLASH atrás das caches). A imagem da FLASH começa nele, a da SDRAM em `act.sdram_base`, e o boot ROM só salta para a FLASH. Sem padrão. |
| `act.flash_words` | Palavras do armazenamento da FLASH na FPGA: um ELF com código maior é reportado e não executado. Usado só na placa. |
| `act.ram_tests` | Nomes dos ELFs que reescrevem o próprio código e por isso rodam de uma variante do alvo, com o corpo do teste na RAM (padrão vazio). O relatório tem uma entrada por teste. |
| `act.ram_target_config` | O `test_config.yaml` da variante, cujo script de ligação põe o corpo do teste em memória gravável. Obrigatório com `act.ram_tests`. |
| `act.ram_extensions` | Extensões que a variante compila; as de `act.extensions` quando vazio. |

## Pré-requisitos

- A toolchain GCC RISC-V (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) no `PATH`, que a imagem `ci-elf` do [insper-riscv/Infra](https://github.com/insper-riscv/Infra) já traz, ou instalada como no `manual/GCC_SETUP.md` dele, para o build do próprio ACT4.
- O extra `sim` (`uv sync`) e o GHDL no `PATH`.
- A toolchain Ruby, Bundler e UDB do ACT4, e o checkout do ACT4 para o qual a chave `act.vendor_dir` aponta.

## Testes

Não há teste automatizado neste repositório. O workflow de certificação de um projeto consumidor o executa.

## Uso

```bash
uv sync
uv run riscv-tools --config /path/to/project/config.yaml certify
```

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
