# Criando um workflow do GitHub Actions por tarefa

O `riscv-tools` não traz "o" workflow de CI único: tarefas diferentes precisam de runners e gatilhos diferentes, e juntá-las num só workflow deixa cada uma mais lenta e mais difícil de raciocinar. Divida por tarefa: um workflow por preocupação, cada um com o gatilho e o runner que realmente combinam.

| Tarefa | Precisa de | Gatilho típico |
|---|---|---|
| Testes só de simulação | A imagem `ci-elf` (GHDL, GCC RISC-V, Spike, uv, Python e cocotb) num runner hospedado do GitHub | Todo push/PR |
| Testes em hardware real | Um runner self-hosted com Quartus, a placa e o cabo JTAG, executando a imagem `ci-elf` num contêiner | Push na branch principal, ou `workflow_dispatch` |
| Regenerar goldens | A imagem `ci-elf` (GCC e Spike) num runner hospedado, sem hardware | `workflow_dispatch`, sob demanda |

## 1. As imagens de CI

As imagens vêm do [insper-riscv/Infra](https://github.com/insper-riscv/Infra) e já trazem tudo o que um job precisa, então um workflow não instala toolchain nem `uv`: ele roda o job dentro da imagem.

| Imagem | Acrescenta | Use para |
|---|---|---|
| `ghcr.io/insper-riscv/ci-vhdl` | GHDL, Yosys, `uv`, Python 3.14, cocotb | Jobs que só simulam VHDL |
| `ghcr.io/insper-riscv/ci-elf` | O GCC RISC-V com picolibc e o Spike | Jobs que compilam testes e rodam o `riscv-tools` |
| `ghcr.io/insper-riscv/ci-act4` | As dependências do ACT4 | `certify` |

`latest` é a última publicação. Para uma execução reproduzível, use a tag `sha-<commit>` da publicação desejada.

O projeto consumidor depende deste repositório como submódulo (normalmente `tools/Tools`) e lista o `riscv-tools` como dependência de caminho editável no próprio `pyproject.toml`, então o `uv sync` na raiz do projeto instala tudo e o `uv run riscv-tools` funciona de lá. Todo job abaixo começa do mesmo jeito:

```yaml
runs-on: ubuntu-26.04
container:
  image: ghcr.io/insper-riscv/ci-elf:latest
steps:
  - uses: actions/checkout@v7
    with:
      submodules: true
  - run: uv sync
```

O `submodules: true` é o que traz este repositório. Se a configuração do projeto cita repositórios irmãos (como o `../Core`), o job também os clona ao lado do checkout, já que um checkout de CI não tem um diretório pai com eles.

## 2. Testes só de simulação

O mais barato de rodar: sem hardware e sem runner self-hosted. O `sim` dirige o cocotb/GHDL contra o `.hex` de cada teste, consultando a mesma convenção de `tohost` do hardware real (veja [configuration.md](configuration.md#sim) para as chaves de `sim:`). O seu projeto ainda fornece o próprio `sim.test_module`, o teste cocotb que conhece os nomes reais dos sinais VHDL do projeto sob teste.

```yaml
name: sim
on: [push, pull_request]

concurrency:
  group: sim-${{ github.ref }}
  cancel-in-progress: true

jobs:
  sim:
    runs-on: ubuntu-26.04
    container:
      image: ghcr.io/insper-riscv/ci-elf:latest

    steps:
      - uses: actions/checkout@v7
        with:
          submodules: true
      - run: uv sync

      - run: uv run riscv-tools --config config.yaml generate-header
      - run: uv run riscv-tools --config config.yaml compile --emit hex
      - run: uv run riscv-tools --config config.yaml sim

      - name: Upload waveforms
        if: failure()
        uses: actions/upload-artifact@v7
        with:
          name: waveforms
          path: "**/*.ghw"
          if-no-files-found: ignore
```

O `compile` também gera, no Spike, o golden de todo teste `memory` em C, e por isso este job precisa da imagem `ci-elf` e não só da `ci-vhdl`.

## 3. Testes em hardware real

Precisa de um runner self-hosted com Quartus, a placa e o cabo JTAG. A configuração dele está nos guias `RUNNER_SETUP.md` e `QUARTUS_INSTALL.md` do Infra. O host fornece só o Quartus, o Docker, o servidor JTAG (`jtagd`) e o runner: o job roda todo o resto na imagem `ci-elf`, com o Quartus montado somente para leitura.

O bloco `concurrency` importa aqui. Cancelar uma execução no meio de um `quartus_pgm` deixa a placa programada pela metade, então todas as refs compartilham um grupo e o `cancel-in-progress` fica `false`. Uma execução manual também pede um campo `confirm` que precisa ser igual a um secret do repositório, como segunda checagem além do acesso de escrita, que já controla quem pode disparar.

```yaml
name: real
on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      confirm:
        description: "Valor do secret FPGA_RUN_SECRET"
        required: true

concurrency:
  group: physical-fpga
  cancel-in-progress: false

jobs:
  real:
    runs-on: [self-hosted, quartus, fpga]   # os rótulos com que o seu runner foi registrado
    env:
      IMAGE: ghcr.io/insper-riscv/ci-elf:latest

    steps:
      - name: Authorize manual run
        if: github.event_name == 'workflow_dispatch'
        run: |
          [ "${{ inputs.confirm }}" = "${{ secrets.FPGA_RUN_SECRET }}" ] \
            || { echo "::error::confirmation does not match"; exit 1; }

      - uses: actions/checkout@v7
        with:
          submodules: true

      - run: docker pull "$IMAGE"

      # o jtagconfig inicia o jtagd do host se nenhum estiver rodando.
      - name: Start the JTAG server of the host
        run: /opt/altera_lite/25.1std/quartus/bin/jtagconfig

      - name: Build, program and run
        run: |
          docker run --rm --network host --userns=host \
            --user "$(id -u):$(id -g)" -e HOME=/tmp/h \
            -v /opt/altera_lite:/opt/altera_lite:ro \
            -v "$PWD:/workspace" -w /workspace "$IMAGE" bash -c '
              export PATH=/opt/altera_lite/25.1std/quartus/bin:$PATH
              uv sync
              uv run riscv-tools --config config.yaml generate-header
              uv run riscv-tools --config config.yaml compile --emit mif
              uv run riscv-tools --config config.yaml run'
```

| Opção | Para que serve |
|---|---|
| `-v /opt/altera_lite:/opt/altera_lite:ro` | A instalação do Quartus do host, somente leitura; a imagem não traz nenhuma |
| `--network host` | O `jtagd` do host escuta em `localhost:1309`, e o programador dentro do contêiner se conecta a ele ali |
| `--user "$(id -u):$(id -g)"` e `-e HOME=/tmp/h` | Os arquivos que o build escreve pertencem ao usuário do runner, e o Quartus tem um home gravável |
| `--userns=host` | Mantém o `--network host` válido num daemon do Docker que remapeia usuários, e não faz nada num que não remapeia |

## 4. Regenerando goldens

Só sob demanda: `workflow_dispatch`, não a cada push. Precisa do Spike e do GCC RISC-V, não de hardware, então roda num runner hospedado, dentro da imagem `ci-elf`.

Os testes `memory` em C não precisam disto, já que o `compile` regenera o golden deles toda vez. Os goldens a regenerar são os versionados, ao lado do `src.S` de um teste em assembly (veja [creating-an-asm-test.md](creating-an-asm-test.md)). Há uma lacuna que a CLI não disfarça: o `generate-golden` precisa de `--start`/`--end` para o intervalo de bytes a capturar, e isso não fica registrado em lugar nenhum para um teste *novo*, então você ainda escolhe à mão na primeira vez. O que o CI *consegue* automatizar por completo é **re**gerar goldens já existentes (por exemplo depois de uma mudança de RTL ou de toolchain, para confirmar que os valores esperados não mudaram), lendo o intervalo de endereços do próprio golden JSON existente:

```yaml
name: regenerate-goldens
on: workflow_dispatch

jobs:
  regenerate:
    runs-on: ubuntu-26.04
    container:
      image: ghcr.io/insper-riscv/ci-elf:latest

    steps:
      - uses: actions/checkout@v7
        with:
          submodules: true
      - run: uv sync

      - run: uv run riscv-tools --config config.yaml compile --emit mif

      - name: Regenerate every existing golden
        run: |
          for golden in asm/*/golden.json; do
            [ -f "$golden" ] || continue
            name=$(basename "$(dirname "$golden")")
            elf="build/real/$name.elf"
            march=$(jq -r --arg n "$name" '.[] | select(.name == $n) | .march' build/real/manifest.json)
            # As chaves têm sempre a mesma largura, preenchidas com zeros
            # (o formato em que um golden JSON é escrito), então o
            # mínimo/máximo lexicográfico já é igual ao numérico. Só o
            # "+1" do fim exclusivo precisa de aritmética de verdade, que
            # o bash faz nativamente com literais 0x.
            start=$(jq -r 'keys | min' "$golden")
            max_key=$(jq -r 'keys | max' "$golden")
            end=$(printf '0x%X' $((max_key + 1)))
            uv run riscv-tools --config config.yaml generate-golden "$elf" \
                --march "$march" --start "$start" --end "$end" --out "$golden"
          done

      # depois faça diff/commit/abra um PR com o que mudou, usando os seus
      # próprios passos de git: regenerar sozinho nunca dá push em nada
```

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../LICENSE).
