# Criando um workflow do GitHub Actions por tarefa

O `riscv-tools` não traz "o" workflow de CI único: tarefas diferentes precisam
de runners e gatilhos diferentes, e juntá-las num só workflow deixa cada uma
mais lenta e mais difícil de raciocinar. Divida por tarefa: um workflow por
preocupação, cada um com o gatilho e o runner que realmente combinam.

| Tarefa | Precisa de | Gatilho típico |
|---|---|---|
| Testes só de simulação | Só a toolchain GCC; qualquer runner hospedado do GitHub | Todo push/PR |
| Testes em hardware real | Um runner self-hosted com a placa + cabo JTAG conectados | Todo push/PR, ou `workflow_dispatch` se o tempo de hardware for escasso |
| Regenerar goldens | A toolchain GCC + um Spike compilado (sem hardware) | `workflow_dispatch`, sob demanda |

Todo job abaixo começa do mesmo jeito: fazer o checkout e preparar o `uv`. O
`submodules: true` é o que traz este repositório quando ele é um submódulo do
projeto consumidor:

```yaml
steps:
  - uses: actions/checkout@v4
    with:
      submodules: true
  - uses: astral-sh/setup-uv@v3
  - run: uv sync
    working-directory: Tools   # onde este repositório for feito o checkout, em relação ao seu projeto
```

## Testes só de simulação

O mais barato de rodar: sem hardware, sem runner self-hosted, só a toolchain
RISC-V, o GHDL e o extra `sim` (cocotb + cocotb-tools; veja
[configuration.md](configuration.md#sim-exige-o-extra-sim-uv-sync---extra-sim)
para as chaves de config `sim:` de que o `sim_runner` precisa). O
`sim_runner`/`riscv-tools sim` dirige o cocotb/GHDL contra o `.hex` de cada
teste, consultando a mesma convenção de mailbox PASS/FAIL do hardware real: o
seu projeto ainda fornece o próprio `sim.test_module` (o teste cocotb que
conhece os nomes reais dos sinais VHDL do DUT), e o `sim_runner` só o roda por
teste e coleta os resultados.

```yaml
name: sim
on: [push, pull_request]

jobs:
  sim:
    runs-on: ubuntu-latest
    container:
      image: ghdl/ghdl:6.0.0-mcode-ubuntu-24.04   # já traz o GHDL instalado

    steps:
      - uses: actions/checkout@v4
        with:
          submodules: true
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra sim
        working-directory: Tools

      # o seu próprio passo de instalação da toolchain aqui (riscv32-unknown-elf-gcc no PATH)

      - run: uv run riscv-tools --config ../config.yaml --root .. compile --emit hex
        working-directory: Tools
      - run: uv run riscv-tools --config ../config.yaml --root .. sim
        working-directory: Tools

      - name: Upload waveforms
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: waveforms
          path: "**/*.ghw"
          if-no-files-found: ignore
```

## Testes em hardware real

Precisa de um runner self-hosted com a placa e o cabo JTAG fisicamente
conectados: veja a doc de setup do seu runner para saber como isso é
configurado. O detalhe de CI que importa aqui é o `concurrency`: o
comportamento padrão do gatilho de push cancela em silêncio uma execução
superada, o que é perigoso no meio de um `quartus_pgm` (deixa a placa
parcialmente programada); fixe `cancel-in-progress: false` para que uma
execução sempre termine antes de a próxima começar.

```yaml
name: real
on:
  push:
  workflow_dispatch:

concurrency:
  group: real-${{ github.ref }}
  cancel-in-progress: false

jobs:
  real:
    runs-on: [self-hosted, fpga]   # o rótulo com que o seu runner foi registrado
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: true
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
        working-directory: Tools

      - run: uv run riscv-tools --config ../config.yaml --root .. compile --emit mif
        working-directory: Tools
      - run: uv run riscv-tools --config ../config.yaml --root .. run
        working-directory: Tools
```

## Regenerando goldens

Só sob demanda: `workflow_dispatch`, não a cada push. Precisa do Spike e do GCC
RISC-V, não de hardware, então roda em qualquer runner preparado como no
[insper-riscv/Infra](https://github.com/insper-riscv/Infra)
(`GCC_SETUP.md` e `SPIKE_SETUP.md`).

Há uma lacuna real que a CLI não disfarça: o `generate-golden` precisa de
`--start`/`--end` para o intervalo de bytes a capturar, e isso não fica
registrado em lugar nenhum para um teste *novo*: você ainda escolhe à mão na
primeira vez (veja
[creating-a-c-test.md](creating-a-c-test.md#testes-unit-versus-memory)). O que
o CI *consegue* automatizar por completo é **re**gerar goldens já existentes
(por exemplo depois de uma mudança de RTL ou de toolchain, para confirmar que
os valores esperados não mudaram), lendo o intervalo de endereços do próprio
golden JSON existente e rodando o `generate-golden` de novo sobre o mesmo
intervalo:

```yaml
name: regenerate-goldens
on: workflow_dispatch

jobs:
  regenerate:
    runs-on: self-hosted   # um runner preparado como no insper-riscv/Infra
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: true
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
        working-directory: Tools

      - run: uv run riscv-tools --config ../config.yaml --root .. compile --emit mif
        working-directory: Tools

      - name: Regenerate every existing golden
        working-directory: Tools
        run: |
          # golden.json só existe ao lado de src.c/src.S para testes do
          # tipo "memory" (veja creating-a-c-test.md); todo outro teste
          # não tem nada a regenerar aqui.
          for golden in ../c/*/golden.json ../asm/*/golden.json; do
            [ -f "$golden" ] || continue
            name=$(basename "$(dirname "$golden")")
            elf="../build/real/$name.elf"
            march=$(jq -r --arg n "$name" '.[] | select(.name == $n) | .march' ../build/real/manifest.json)
            # o jq não tem função para interpretar hex, mas as chaves têm
            # sempre a mesma largura, preenchidas com zeros (o formato do
            # próprio write_golden_json), então o mínimo/máximo
            # lexicográfico já é igual ao numérico; só o "+1" do fim
            # exclusivo precisa de aritmética de verdade, que o $(( )) do
            # bash faz nativamente com literais 0x.
            start=$(jq -r 'keys | min' "$golden")
            max_key=$(jq -r 'keys | max' "$golden")
            end=$(printf '0x%X' $((max_key + 1)))
            uv run riscv-tools --config ../config.yaml generate-golden "$elf" \
                --march "$march" --start "$start" --end "$end" --out "$golden"
          done

      # depois faça diff/commit/abra um PR com o que mudou, usando os seus
      # próprios passos de git: regenerar sozinho nunca dá push em nada
```

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../LICENSE).
