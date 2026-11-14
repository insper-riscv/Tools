# RISC-V Tools

🌐 [Português](README.md) · [English](README.en.md)

O `riscv-tools` é um pacote Python que compila, simula, executa e certifica programas de teste para RISC-V bare-metal. Cada projeto descreve o seu fluxo em um `config.yaml`, e o mesmo teste compilado roda de duas formas: no hardware real, pela porta JTAG, ou na simulação cocotb/GHDL.

Os resultados são conferidos contra referências (goldens), geradas pelo Spike ou versionadas no repositório do projeto.

O pacote tem um módulo por responsabilidade, cada um com o seu `__config__.py` de valores padrão. O `config.yaml` do projeto consumidor sobrescreve esses padrões, e a referência completa está em [docs/configuration.md](docs/pt-br/configuration.md).

Ele foi projetado para rodar em uma workstation com todas as ferramentas instaladas, ou dentro das imagens Docker de CI do repositório [Infra](https://github.com/insper-riscv/Infra).

## Módulos

| Módulo               | Responsabilidade                                            | Doc |
|----------------------|--------------------------------------------------------------|-----|
| `compiler`           | .c/.S -> .elf/.bin, leitura dos cabeçalhos (`RV32_EXT`/`RV32_TEST_KIND`/`RV32_TIMEOUT_S`) | [docs/modules/compiler.md](docs/pt-br/modules/compiler.md) |
| `bin_to_image`       | .bin -> .mif/.hex (formatos de imagem de memória, sem compilador) | [docs/modules/bin_to_image.md](docs/pt-br/modules/bin_to_image.md) |
| `c_to_asm`           | .c -> assembly RISC-V legível (`gcc -S`), para inspecionar a geração de código | [docs/modules/c_to_asm.md](docs/pt-br/modules/c_to_asm.md) |
| `boot_memory`           | Compila o bootloader fixo e compartilhado, uma vez, reutilizado em todos os testes | [docs/modules/boot_memory.md](docs/pt-br/modules/boot_memory.md) |
| `jtag`               | Detecção do cabo JTAG em tempo real, executor genérico de `.tcl` | [docs/modules/jtag.md](docs/pt-br/modules/jtag.md) |
| `board`              | Identificação, seleção e trava da placa pelo JTAG | [docs/modules/board.md](docs/pt-br/modules/board.md) |
| `mem_edit`           | Primitivas genéricas do In-System Memory Content Editor (ler/escrever palavra, escrita completa, dump) | [docs/modules/mem_edit.md](docs/pt-br/modules/mem_edit.md) |
| `flash_loader`       | Grava a FLASH interna de uma só cópia pelo carregador JTAG   | [docs/modules/flash_loader.md](docs/pt-br/modules/flash_loader.md) |
| `flash_image`        | Empacota um programa na imagem de uma banca da FLASH (cabeçalho, CRC, versão), confere a imagem e a envia pela UART JTAG | [docs/modules/flash_image.md](docs/pt-br/modules/flash_image.md) |
| `rom_writer`         | Grava uma imagem de ROM via JTAG sem reprogramar            | [docs/modules/rom_writer.md](docs/pt-br/modules/rom_writer.md) |
| `ram_zero`           | Zera a RAM inteira via JTAG sem reprogramar                 | [docs/modules/ram_zero.md](docs/pt-br/modules/ram_zero.md) |
| `ram_target`         | Onde fica a RAM (instância da FPGA ou porta de debug da SDRAM) | [docs/modules/ram_target.md](docs/pt-br/modules/ram_target.md) |
| `ram_load`           | Carrega arquivos na SDRAM pela porta de debug, confere e dispara | [docs/modules/ram_load.md](docs/pt-br/modules/ram_load.md) |
| `sdram_debug`        | Lê, escreve e preenche a SDRAM pela porta de debug JTAG      | [docs/modules/sdram_debug.md](docs/pt-br/modules/sdram_debug.md) |
| `uart_console`       | Mostra a saída do programa pela UART JTAG enquanto ele roda  | [docs/modules/uart_console.md](docs/pt-br/modules/uart_console.md) |
| `display`            | Lê e escreve o registrador do display de sete segmentos e a bandeira de falha da placa, com que o `run` e o `certify-board` mostram o programa em execução | [docs/modules/display.md](docs/pt-br/modules/display.md) |
| `ram_dump`           | Faz o dump da RAM inteira via JTAG para um `.mif`           | [docs/modules/ram_dump.md](docs/pt-br/modules/ram_dump.md) |
| `htif`               | Leitura do `tohost` e escrita do `fromhost` de reinício       | [docs/modules/htif.md](docs/pt-br/modules/htif.md) |
| `quartus_program`    | Recompilação completa + `quartus_pgm` (o caminho lento, "base") | [docs/modules/quartus_program.md](docs/pt-br/modules/quartus_program.md) |
| `mem_validator`      | Compara um dump de RAM com um golden JSON                   | [docs/modules/mem_validator.md](docs/pt-br/modules/mem_validator.md) |
| `golden_generator`   | Gera um golden JSON dinamicamente rodando um ELF no Spike   | [docs/modules/golden_generator.md](docs/pt-br/modules/golden_generator.md) |
| `spike_exec`         | Prepara e dispara execuções do Spike: preflight, símbolos do ELF, linha de comando (compartilhado por `golden_generator` e `spike_run`) | [docs/modules/spike_exec.md](docs/pt-br/modules/spike_exec.md) |
| `spike_run`          | Roda cada teste compilado até o fim no Spike e reporta PASS/FAIL pelo veredito HTIF, sem hardware | [docs/modules/spike_run.md](docs/pt-br/modules/spike_run.md) |
| `orchestrator`       | Compõe os módulos acima numa rodada completa de testes em hardware real | [docs/modules/orchestrator.md](docs/pt-br/modules/orchestrator.md) |
| `sim_runner`         | Dirige a simulação cocotb/GHDL: a contraparte de simulação do `orchestrator` (precisa do extra `sim`) | [docs/modules/sim_runner.md](docs/pt-br/modules/sim_runner.md) |
| `certify`            | Compila e roda a suíte de certificação arquitetural ACT4 sob cocotb/GHDL | [docs/modules/certify.md](docs/pt-br/modules/certify.md) |
| `vhdl_sort`          | Ordena topologicamente fontes VHDL por dependência de entidade/pacote, para o `-a` do GHDL | [docs/modules/vhdl_sort.md](docs/pt-br/modules/vhdl_sort.md) |
| `memory_map`         | Confere que todas as cópias escritas à mão do mapa de memória concordam com o YAML da plataforma | [docs/modules/memory_map.md](docs/pt-br/modules/memory_map.md) |
| `path_check`         | Falha quando um caminho de arquivo listado na configuração do projeto não existe (antes e depois de mover arquivos) | [docs/modules/path_check.md](docs/pt-br/modules/path_check.md) |
| `tree_check`         | Falha quando a árvore de um repositório sai do layout que todos compartilham: arquivos padrão, pares de idioma, `.vhd` em `src/`, Common-Components em `src/common`, nomes de pasta, o manifesto `provides` e a cobertura de testes e provas | [docs/modules/tree_check.md](docs/pt-br/modules/tree_check.md) |
| `sources`            | Emite a lista ordenada dos arquivos de um alvo, lida dos manifestos `provides` dos repositórios | [docs/modules/sources.md](docs/pt-br/modules/sources.md) |
| `ipxact` | Gera e confere as descrições IP-XACT (IEEE 1685-2022) dos blocos VHDL: extrai portas e generics com o GHDL, escreve o `ipxact:component` e valida contra o esquema da Accellera e as regras semânticas do padrão | [docs/modules/ipxact.md](docs/pt-br/modules/ipxact.md) |
| `vhdl_style`         | Roda o VSG com a configuração e as cinco regras locais do projeto (cabeçalho, bibliotecas, sem `component`, `port map` por nome, docstring por declaração) e traz os subcomandos `vsg-config`, `vsg-rules` e `vhdl-files`; deixa de fora `vendor/` e os IPs do Quartus | [docs/modules/vhdl_style.md](docs/pt-br/modules/vhdl_style.md) |
| `board_schema`       | Lê e confere o `board.yaml`, o `pins.yaml`, a família e o chip do catálogo de placas e os campos novos do `platform.yaml` | [docs/modules/board_schema.md](docs/pt-br/modules/board_schema.md) |
| `board_check`        | Confere o que a plataforma exige contra o que as placas oferecem (regras V1 a V22) | [docs/modules/board_check.md](docs/pt-br/modules/board_check.md) |
| `platform_sync`      | Escreve o `config.yaml` de uma plataforma para o projeto que a consome, com a pasta do submódulo na frente de cada caminho dela | [docs/modules/platform_sync.md](docs/pt-br/modules/platform_sync.md) |
| `new_project`        | Cria um projeto para uma placa conhecida: baixa o `Insper-RISC-V`, copia a plataforma da placa, escreve o `platform.yaml` a partir do perfil e do desenho de memória, registra a plataforma, gera os arquivos e imprime um help curto (`riscv-tools new-project`) | [docs/modules/new_project.md](docs/pt-br/modules/new_project.md) |
| `project` | Comandos curtos para um projeto criado por `new-project` (`project build`, `flash`, `doctor` e `help`) e o script `rt`, que roda o `riscv-tools` na imagem `dev_tools` com o Quartus do computador | [docs/modules/project.md](docs/pt-br/modules/project.md) |
| `profiles`           | Lista os perfis válidos de um core a partir das extensões e das regras entre elas (M e Zmmul não coexistem, Zicntr e Zihpm implicam Zicsr) | [docs/modules/profiles.md](docs/pt-br/modules/profiles.md) |
| `timing_paths`       | Lista os piores caminhos de setup de um projeto do Quartus compilado, por registrador | [docs/modules/timing_paths.md](docs/pt-br/modules/timing_paths.md) |
| `quartus_reports`    | Lê os resumos de recursos do Quartus (`*.map.summary`, `*.map.rpt`, `*.fit.summary`, `*.fit.rpt`) de todas as famílias | [docs/modules/quartus_reports.md](docs/pt-br/modules/quartus_reports.md) |
| `fit_estimate`       | Estima se um perfil cabe numa placa com a tabela de calibração da família e julga o relatório do ajuste (passa até 85 %, aviso até 100 %, erro acima; V11 a V14 e V18) | [docs/modules/fit_estimate.md](docs/pt-br/modules/fit_estimate.md) |
| `calibration`        | Mede os perfis de uma família com o comando de compilação do projeto (`quartus_map`) e ajusta por mínimos quadrados os coeficientes do estimador | [docs/modules/calibration.md](docs/pt-br/modules/calibration.md) |
| `run_log`            | Rotaciona e replica (tee) toda a saída de console de uma execução num histórico de logs persistente por tipo | [docs/modules/run_log.md](docs/pt-br/modules/run_log.md) |
| `board_inputs` | Lê o `platform.yaml`, o `board.yaml`, o `pins.yaml`, a família e os chips que um gerador consome | [docs/modules/board_inputs.md](docs/pt-br/modules/board_inputs.md) |
| `board_ports` | Monta as portas do topo de uma placa (nome, largura, direção e pino de cada bit) a partir dos papéis | [docs/modules/board_ports.md](docs/pt-br/modules/board_ports.md) |
| `board_video` | Resolve o vídeo que a plataforma pede numa placa (modo, proporção, canal de cor, relógio de pixel e framebuffer) e entrega os generics de temporização ao topo | [docs/modules/board_video.md](docs/pt-br/modules/board_video.md) |
| `board_clocks` | Decide os relógios por papel (`mem`, `mem_pin`, `fetch`, `core`) com frequência e fase | [docs/modules/board_clocks.md](docs/pt-br/modules/board_clocks.md) |
| `chip_package` | Gera o pacote VHDL com os tempos de um chip do catálogo e entrega os atrasos de E/S ao `.sdc` | [docs/modules/chip_package.md](docs/pt-br/modules/chip_package.md) |
| `pin_assignments` | Escreve as atribuições de pino e de padrão de E/S do `.qsf`, derivando as demais do papel | [docs/modules/pin_assignments.md](docs/pt-br/modules/pin_assignments.md) |
| `pll_generator` | Calcula os contadores do PLL e escreve a primitiva da família (`altera_pll` na Cyclone V e `altpll` nas demais famílias) | [docs/modules/pll_generator.md](docs/pt-br/modules/pll_generator.md) |
| `sdc_generator` | Gera o `.sdc` com relógios, atrasos de E/S do chip, caminhos de leitura e cruzamentos de domínio | [docs/modules/sdc_generator.md](docs/pt-br/modules/sdc_generator.md) |
| `quartus_project` | Gera o `.qpf` e o `.qsf` (sem os pinos) com família, dispositivo e a lista de fontes | [docs/modules/quartus_project.md](docs/pt-br/modules/quartus_project.md) |
| `top_generator` | Gera o topo fino da placa, que só liga o PLL, o SoC, um backend por região e o anel de pinos | [docs/modules/top_generator.md](docs/pt-br/modules/top_generator.md) |
| `board_generate` | Compõe os geradores no projeto Quartus de uma plataforma numa placa (`riscv-tools board generate`) | [docs/modules/board_generate.md](docs/pt-br/modules/board_generate.md) |
| `board_equivalence` | Compara o projeto gerado com os arquivos escritos à mão: pinos, restrições, PLL, fontes e atribuições | [docs/modules/board_equivalence.md](docs/pt-br/modules/board_equivalence.md) |

## Docs

- [AUTHORS.md](AUTHORS.md): autores com commits no repositório, com nome e conta do GitHub.
- [CONTRIBUTING.md](CONTRIBUTING.md): regras obrigatórias de contribuição e verificação antes de abrir Pull Request.
- [CITATION.cff](CITATION.cff): metadados para citação do software.
- [Referência de configuração](docs/pt-br/configuration.md)
- [Criando um teste em C](docs/pt-br/creating-a-c-test.md)
- [Criando um teste em ASM](docs/pt-br/creating-an-asm-test.md)
- [Gerando um golden JSON pelo Spike](docs/pt-br/generating-a-golden.md)
- [Criando um workflow do GitHub Actions por tarefa](docs/pt-br/github-actions.md)
- [Adicionando uma placa nova](https://github.com/insper-riscv/Insper-RISC-V/blob/main/docs/pt-br/guide/adicionar-placa.md), guia do Insper-RISC-V que usa os comandos `check-boards`, `check-memory-map`, `board`, `program` e `calibrate`

## Uso

```bash
uv sync
uv run riscv-tools --config /path/to/project/config.yaml compile --emit mif
uv run riscv-tools --config /path/to/project/config.yaml compile --emit mif --only test-a,test-b
uv run riscv-tools --config /path/to/project/config.yaml compile --emit asm
uv run riscv-tools --config /path/to/project/config.yaml run
uv run riscv-tools --config /path/to/project/config.yaml run --exclude test-a,test-b
uv run riscv-tools --config /path/to/project/config.yaml generate-golden \
    build/real/some_test.elf --march rv32im --start 0x10 --end 0x20 --out golden/some_test.json

# Simulação (precisa do extra "sim": cocotb + cocotb-tools, e do GHDL no PATH)
uv sync
uv run riscv-tools --config /path/to/project/config.yaml compile --emit hex
uv run riscv-tools --config /path/to/project/config.yaml sim
uv run riscv-tools --config /path/to/project/config.yaml sim --only test-a,test-b
```

Veja `riscv-tools --help` para a lista completa de subcomandos (`compile`, `generate-header`, `generate-golden`, `write-rom`, `zero-ram`, `dump-ram`, `load-ram`, `console`, `display`, `program`, `htif read|restart`, `run`, `spike-run`, `sim`, `certify`, `certify-board`, `profiles`, `vhdl-sort`, `check-memory-map`, `generate-memory-map`, `generate-config-pkg`, `check-paths`, `check-boards`, `check-tree`, `sources`, `ipxact`, `check-vhdl-style`, `vsg-config`, `vsg-rules`, `vhdl-files`, `platform`, `flash-image`, `timing-paths`, `board generate`, `calibrate` e `check-fit`).

```bash
# vhdl-sort não precisa de --config; é só análise do conteúdo dos arquivos,
# por exemplo ligado ao alvo de checagem de sintaxe VHDL de um Makefile:
uv run riscv-tools vhdl-sort src/**/*.vhd
```

## Desenvolvimento

```bash
uv sync --group dev
uv run pytest
```

Os testes que precisam do GHDL, do GCC RISC-V ou do Spike são pulados quando a
ferramenta não existe. A doc de cada módulo lista seus pré-requisitos e os
testes que o cobrem. Os testes verificam o tooling deste pacote; o processador
é verificado pelas suítes do projeto consumidor.

`tests/test_static_analysis.py` roda `ruff`, `pyright` e `deptry` sobre o
pacote inteiro, por isso não pertence a nenhum módulo em particular.

### Rodando os testes no Docker

O `Dockerfile` parte da imagem `ci-elf` que o
[insper-riscv/Infra](https://github.com/insper-riscv/Infra) publica
(`ghcr.io/insper-riscv/ci-elf`, veja o `docs/pt-br/docker/ci-elf.md` dele):
GHDL, o GCC RISC-V com picolibc, o Spike com o módulo de debug longe do endereço 0
e o `uv`. Ele acrescenta as dependências deste projeto, de modo que nada é pulado e
nada é compilado:

```bash
docker build -t riscv-tools-tests .
docker run --rm -v "$PWD:/workspace" riscv-tools-tests
docker run --rm -v "$PWD:/workspace" riscv-tools-tests tests/test_sim_runner.py -v
```

A imagem base é a `latest` da `ci-elf`. Para testar contra uma
publicação específica, passe a tag `sha-` dela:

```bash
docker build --build-arg TOOLCHAIN_IMAGE=ghcr.io/insper-riscv/ci-elf:sha-<commit> \
    -t riscv-tools-tests .
```

O workflow `tests` monta esta imagem e roda a suíte inteira a cada push e pull
request.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](LICENSE).
