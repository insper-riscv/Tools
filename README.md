# RISC-V Tools

🌐 [Português](README.md) · [English](README.en.md)

Ferramentas de build e teste dirigidas por configuração, para RISC-V bare-metal
ou simulação de hardware virtual: o mesmo teste compilado roda contra o
hardware real via JTAG ou contra a simulação cocotb/GHDL; os resultados podem
ser verificados contra referências (goldens) geradas pelo Spike ou versionadas
no repositório. Organizado como um módulo por responsabilidade, cada um com o
próprio `__config__.py` de padrões; o projeto consumidor fornece o seu
`config.yaml`, que sobrescreve esses padrões. Veja
[docs/configuration.md](docs/pt-br/configuration.md) para a referência completa.

## Módulos

| Módulo               | Responsabilidade                                            | Doc |
|----------------------|--------------------------------------------------------------|-----|
| `compiler`           | .c/.S -> .elf/.bin, leitura dos cabeçalhos (`RV32_EXT`/`RV32_TEST_KIND`/`RV32_TIMEOUT_S`) | [docs/modules/compiler.md](docs/pt-br/modules/compiler.md) |
| `bin_to_image`       | .bin -> .mif/.hex (formatos de imagem de memória, sem compilador) | [docs/modules/bin_to_image.md](docs/pt-br/modules/bin_to_image.md) |
| `c_to_asm`           | .c -> assembly RISC-V legível (`gcc -S`), para inspecionar a geração de código | [docs/modules/c_to_asm.md](docs/pt-br/modules/c_to_asm.md) |
| `boot_rom`           | Compila o bootloader fixo e compartilhado, uma vez, reutilizado em todos os testes | [docs/modules/boot_rom.md](docs/pt-br/modules/boot_rom.md) |
| `jtag`               | Detecção do cabo JTAG em tempo real, executor genérico de `.tcl` | [docs/modules/jtag.md](docs/pt-br/modules/jtag.md) |
| `mem_edit`           | Primitivas genéricas do In-System Memory Content Editor (ler/escrever palavra, escrita completa, dump) | [docs/modules/mem_edit.md](docs/pt-br/modules/mem_edit.md) |
| `rom_writer`         | Grava uma imagem de ROM via JTAG sem reprogramar            | [docs/modules/rom_writer.md](docs/pt-br/modules/rom_writer.md) |
| `ram_zero`           | Zera a RAM inteira via JTAG sem reprogramar                 | [docs/modules/ram_zero.md](docs/pt-br/modules/ram_zero.md) |
| `ram_dump`           | Faz o dump da RAM inteira via JTAG para um `.mif`           | [docs/modules/ram_dump.md](docs/pt-br/modules/ram_dump.md) |
| `mailbox`            | Leitura do mailbox PASS/FAIL e pulso da "go flag" de reinício | [docs/modules/mailbox.md](docs/pt-br/modules/mailbox.md) |
| `quartus_program`    | Recompilação completa + `quartus_pgm` (o caminho lento, "base") | [docs/modules/quartus_program.md](docs/pt-br/modules/quartus_program.md) |
| `mem_validator`      | Compara um dump de RAM com um golden JSON                   | [docs/modules/mem_validator.md](docs/pt-br/modules/mem_validator.md) |
| `golden_generator`   | Gera um golden JSON dinamicamente rodando um ELF no Spike   | [docs/modules/golden_generator.md](docs/pt-br/modules/golden_generator.md) |
| `spike_exec`         | Prepara e dispara execuções do Spike: preflight, símbolos do ELF, linha de comando (compartilhado por `golden_generator` e `spike_run`) | [docs/modules/spike_exec.md](docs/pt-br/modules/spike_exec.md) |
| `spike_run`          | Roda cada teste compilado até o fim no Spike e reporta PASS/FAIL pelo veredito HTIF, sem hardware | [docs/modules/spike_run.md](docs/pt-br/modules/spike_run.md) |
| `orchestrator`       | Compõe os módulos acima numa rodada completa de testes em hardware real, ou num sweep de frequência de clock para achar a Fmax | [docs/modules/orchestrator.md](docs/pt-br/modules/orchestrator.md) |
| `sim_runner`         | Dirige a simulação cocotb/GHDL: a contraparte de simulação do `orchestrator` (precisa do extra `sim`) | [docs/modules/sim_runner.md](docs/pt-br/modules/sim_runner.md) |
| `certify`            | Compila e roda a suíte de certificação arquitetural ACT4 sob cocotb/GHDL | [docs/modules/certify.md](docs/pt-br/modules/certify.md) |
| `vhdl_sort`          | Ordena topologicamente fontes VHDL por dependência de entidade/pacote, para o `-a` do GHDL | [docs/modules/vhdl_sort.md](docs/pt-br/modules/vhdl_sort.md) |
| `memory_map`         | Confere que todas as cópias escritas à mão do mapa de memória concordam com o YAML da plataforma | [docs/modules/memory_map.md](docs/pt-br/modules/memory_map.md) |
| `freq_sweep`         | Reescreve a frequência de clock e as defasagens de um fonte de PLL: o mecanismo com que o sweep de frequência do `orchestrator` edita | [docs/modules/freq_sweep.md](docs/pt-br/modules/freq_sweep.md) |
| `run_log`            | Rotaciona e replica (tee) toda a saída de console de uma execução num histórico de logs persistente por tipo | [docs/modules/run_log.md](docs/pt-br/modules/run_log.md) |

## Regra: um módulo, uma responsabilidade

Cada módulo da tabela acima tem exatamente um trabalho. Ao adicionar ou
alterar código:

- Funcionalidade nova que não cabe na responsabilidade de um módulo existente
  ganha o **seu próprio módulo novo**; não a encaixe no módulo não relacionado
  mais próximo só porque é conveniente importar dele.
- Lógica necessária a **dois ou mais** módulos vira um módulo próprio (ou um
  pequeno helper privado compartilhado por import explícito), em vez de ser
  copiada em cada chamador. Duplicação entre módulos é como uma correção
  aplicada a uma cópia deixa a outra quebrada em silêncio, sem nada nos
  pontos de chamada indicando que existe uma segunda cópia.
- Se houver dúvida entre uma responsabilidade nova e uma que cabe num módulo
  existente, prefira o módulo menor e mais específico: juntar dois módulos
  depois é fácil; desembaraçar um módulo que acumulou vários trabalhos
  distintos não é.

## Dependências da toolchain

Os binários RISC-V (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) vêm de uma
única toolchain GCC e são resolvidos pelo `PATH`; o Spike só é necessário para
gerar goldens.

| Comando | GCC | objcopy | nm | Spike |
|---|---|---|---|---|
| `compile --emit asm` | sim | não | não | não |
| `compile --emit mif` / `--emit hex` | sim | sim | só para testes `memory` escritos em C | só para testes `memory` escritos em C |
| `generate-golden` | não | não | sim | sim |
| `spike-run` | não | sim | sim | sim |
| `program`, `sim` | sim (boot ROM) | sim (boot ROM) | não | não |
| `certify` | sim (pelo build do próprio ACT4) | sim | não | não |

## Instalando a toolchain

A toolchain GCC RISC-V e o Spike vêm da instalação de workstation do
[insper-riscv/Infra](https://github.com/insper-riscv/Infra)
(`GCC_SETUP.md` e `SPIKE_SETUP.md`): os dois ficam num cache compartilhado
(`/opt/riscv-foundation`) e entram no `PATH` por wrappers em
`/usr/local/bin`. Este pacote não compila nada por conta própria.

O Spike precisa manter o módulo de debug longe do endereço 0, o que o build do
Infra faz. Um Spike padrão aborta na inicialização com `devices at [0, 1000)
and [0, 10000) overlap` para um alvo cuja ROM começa no endereço 0; o gerador
de goldens confere isso antes da primeira execução e aponta o
`SPIKE_SETUP.md` quando falha.

## Docs

- [Referência de configuração](docs/pt-br/configuration.md)
- [Criando um teste em C](docs/pt-br/creating-a-c-test.md)
- [Criando um teste em ASM](docs/pt-br/creating-an-asm-test.md)
- [Gerando um golden JSON pelo Spike](docs/pt-br/generating-a-golden.md)
- [Achando a Fmax (sweep de frequência de clock)](docs/pt-br/finding-fmax.md)
- [Criando um workflow do GitHub Actions por tarefa](docs/pt-br/github-actions.md)

## Uso

```bash
uv sync
uv run riscv-tools --config /path/to/project/config.yaml compile --emit mif
uv run riscv-tools --config /path/to/project/config.yaml compile --emit asm
uv run riscv-tools --config /path/to/project/config.yaml run
uv run riscv-tools --config /path/to/project/config.yaml generate-golden \
    build/real/some_test.elf --march rv32im --start 0x10 --end 0x20 --out golden/some_test.json

# Simulação (precisa do extra "sim": cocotb + cocotb-tools, e do GHDL no PATH)
uv sync --extra sim
uv run riscv-tools --config /path/to/project/config.yaml compile --emit hex
uv run riscv-tools --config /path/to/project/config.yaml sim
```

Veja `riscv-tools --help` para a lista completa de subcomandos (`write-rom`,
`zero-ram`, `dump-ram`, `program`, `mailbox read|pulse`, `generate-header`,
`generate-golden`, `spike-run`, `run`, `sim`, `vhdl-sort`, `check-memory-map`, `freq-sweep`).

```bash
# vhdl-sort não precisa de --config; é só análise do conteúdo dos arquivos,
# por exemplo ligado ao alvo de checagem de sintaxe VHDL de um Makefile:
uv run riscv-tools vhdl-sort src/**/*.vhd

# freq-sweep: acha a Fmax editando o PLL e fazendo uma recompilação +
# reprogramação + comparação da RAM completas a cada frequência candidata.
# Veja docs/pt-br/finding-fmax.md.
uv run riscv-tools --config /path/to/project/config.yaml freq-sweep \
    build/real/full.mif --golden golden/full.json --start 1 --stop 30 --step 2
uv run riscv-tools --config /path/to/project/config.yaml freq-sweep \
    build/real/full.mif --golden golden/full.json --binary --low 1 --high 50
```

## Desenvolvimento

```bash
uv sync --group dev --extra sim
uv run pytest
```

Os testes que precisam do GHDL, do GCC RISC-V ou do Spike são pulados quando a
ferramenta não existe. A doc de cada módulo lista seus pré-requisitos e os
testes que o cobrem. Os testes verificam o tooling deste pacote; o processador
é verificado pelas suítes do projeto consumidor.

`tests/test_static_analysis.py` roda `ruff`, `pyright` e `deptry` sobre o
pacote inteiro, por isso não pertence a nenhum módulo em particular.

### Rodando os testes no Docker

O `Dockerfile` parte da imagem de toolchain que o
[insper-riscv/Infra](https://github.com/insper-riscv/Infra) publica
(`ghcr.io/insper-riscv/infra-toolchain`, veja o `TOOLCHAIN_IMAGE.md` dele):
GHDL, o GCC RISC-V com picolibc, um Spike com o patch descrito no
`SPIKE_SETUP.md` e o `uv`, nos mesmos caminhos da instalação de workstation.
Ele acrescenta as dependências deste projeto, de modo que nada é pulado e
nada é compilado:

```bash
docker build -t riscv-tools-tests .
docker run --rm -v "$PWD:/workspace" riscv-tools-tests
docker run --rm -v "$PWD:/workspace" riscv-tools-tests tests/test_sim_runner.py -v
```

A imagem base é a `latest` da imagem de toolchain. Para testar contra uma
publicação específica, passe a tag `sha-` dela:

```bash
docker build --build-arg TOOLCHAIN_IMAGE=ghcr.io/insper-riscv/infra-toolchain:sha-<commit> \
    -t riscv-tools-tests .
```

O workflow `tests` monta esta imagem e roda a suíte inteira a cada push e pull
request.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](LICENSE).
