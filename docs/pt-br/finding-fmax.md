# Achando a Fmax (sweep de frequência de clock)

## Para que serve

A Fmax é a maior frequência de clock em que o seu projeto realmente funciona
no hardware real: não o número que a análise estática de timing do Quartus
*prevê*, mas uma resposta empírica, obtida rodando a placa em frequências
crescentes até ela quebrar. A análise de timing diz se um projeto *deveria*
fechar timing numa dada frequência; rodá-lo é a única forma de saber se ele
realmente calcula a resposta certa lá em cima, já que a variação de tensão,
temperatura e silício, e as lacunas do modelo de timing, não são capturadas só
pela análise estática.

O `riscv-tools freq-sweep` automatiza isso: ele edita repetidamente o PLL do
seu projeto para uma frequência candidata, faz uma recompilação +
reprogramação completas (a frequência do clock é fixada na síntese, então não
existe o atalho mais rápido de recarga por JTAG que existe para testes na
mesma frequência; veja [configuration.md](configuration.md#quartus)), espera o
programa rodar, faz o dump da RAM e compara com um golden JSON, varrendo
linearmente uma faixa ou fazendo busca binária pelo ponto de quebra.

O `freq_sweep`/`orchestrator` leem todo detalhe específico do projeto (o
arquivo do PLL, os nomes dos parâmetros, o caminho do golden) do seu
`config.yaml`, então a mesma lógica de sweep vale para projetos diferentes sem
tocar no código deste pacote.

## Requisitos

- Uma seção `freq_sweep:` na configuração: veja a [referência de
  configuração](configuration.md#freq_sweep-só-necessária-para-riscv-tools-freq-sweep)
  para todas as chaves. No mínimo você precisa de `pll_file` apontando para o
  fonte do PLL do seu projeto; os templates de nome de parâmetro
  (`freq_param_template`/`phase_param_template`) seguem por padrão a convenção
  da megafunção `altpll` do Quartus (`output_clock_frequencyN`/
  `phase_shiftN`) e `phase_count` é `1` por padrão (um PLL simples de fase
  única); sobrescreva só se o seu PLL não combinar.
- Um `.mif` de teste fixo e um golden JSON correspondente: o *mesmo* programa é
  gravado na ROM e conferido em toda frequência candidata, então escolha (ou
  escreva) um que exercite o suficiente do projeto para realmente revelar
  falhas de timing (um programa que quase não toca a memória não dirá muito).
  Veja [creating-a-c-test.md](creating-a-c-test.md#testes-unit-versus-memory)
  e [generating-a-golden.md](generating-a-golden.md) se você ainda não tem um.
- O mesmo setup de hardware real que `run`/`program` exigem: uma placa
  conectada por JTAG, `quartus_sh`/`quartus_pgm` no `PATH`, e
  `quartus.*`/`memory.*` configurados (veja [configuration.md](configuration.md)).

## Como funciona

Para cada frequência candidata, o [`orchestrator`](modules/orchestrator.md):

1. Reescreve o `pll_file` no lugar (veja [freq_sweep](modules/freq_sweep.md)):
   para cada uma das `phase_count` saídas de clock, troca o parâmetro de
   frequência pelo novo valor e recalcula a defasagem dessa saída para que as
   saídas multifase continuem espaçadas proporcionalmente na nova frequência
   (0°, 120°, 240° para um PLL de 3 vias, igualmente espaçadas para qualquer
   outro `phase_count`).
2. Roda uma recompilação e programação completas (veja
   [quartus_program](modules/quartus_program.md), o mesmo caminho lento que o
   fallback de recarga por JTAG do `run` e o `program` usam), com o `.mif` de
   teste fixo gravado como init_file da ROM.
3. Espera `quartus.program_wait_seconds`.
4. Faz o dump da RAM inteira (veja [ram_dump](modules/ram_dump.md)) e compara
   com o golden JSON (veja [mem_validator](modules/mem_validator.md)).

Uma falha de compilação/programação ou de dump da RAM numa frequência
candidata é capturada e registrada como o status daquela candidata, em vez de
abortar o sweep inteiro: uma frequência ruim (por exemplo, uma que falha tanto
em fechar timing que a própria programação dá problema) não deve impedir você
de descobrir o que acontece nas frequências ao redor.

## Rodando um sweep

```bash
# Linear: testa toda frequência de --start a --stop, em passos de --step.
# Para cedo quando 3 candidatas seguidas falham: passado esse ponto a Fmax
# provavelmente já foi achada, então continuar só gasta mais ciclos de
# reconfiguração completa sem informação nova.
uv run riscv-tools --config <project>/config.yaml freq-sweep \
    build/real/full.mif --golden golden/full.json \
    --start 1 --stop 30 --step 2

# Busca binária: converge para a fronteira entre --low (precisa dar PASS) e
# --high (precisa dar FAIL) mais rápido que um sweep linear, ao custo de não
# mostrar o formato da curva de pass/fail abaixo da fronteira.
uv run riscv-tools --config <project>/config.yaml freq-sweep \
    build/real/full.mif --golden golden/full.json \
    --binary --low 1 --high 50
```

Os dois modos escrevem o resultado de cada candidata em `--out` (padrão
`<build_dir>/freq_sweep/freq_sweep_results.json`) conforme avançam, e imprimem
um resumo: a maior frequência que passou num sweep linear, o intervalo
`[lo, hi]` convergido na busca binária:

```json
[
  { "freq_mhz": 1.0, "status": "pass" },
  { "freq_mhz": 3.0, "status": "pass" },
  { "freq_mhz": 5.0, "status": "fail" }
]
```

`status` é um entre `pass`, `fail` (o dump da RAM não bateu com o golden),
`program_fail` (a própria compilação ou programação por JTAG falhou) ou
`dump_fail` (a programação funcionou, mas o dump da RAM falhou).

A tolerância de convergência da busca binária é fixa em 0,5 MHz pela CLI:
chame `orchestrator.run_freq_sweep_binary(..., tolerance=...)` direto do
Python se precisar de um intervalo mais apertado ou mais folgado.

## Interpretando o resultado

- **Sweep linear**: a maior frequência com `status: "pass"` é a sua Fmax
  empírica para *esta* placa, *este* bitstream e quaisquer condições
  ambientes em que ele rodou.
- **Busca binária**: o intervalo final `[lo, hi]` (`lo` PASS, `hi` FAIL); a
  Fmax está em algum ponto entre os dois, estreite mais com uma `tolerance`
  menor se precisar de mais precisão.
- Se o limite superior que você deu (`--stop` ou `--high`) ainda passa, a Fmax
  real é maior que a faixa buscada: rode de novo com uma faixa mais larga.

Tensão e temperatura não são controladas durante um sweep, então o resultado é
empírico para aquela placa específica nas condições em que rodou, e não uma
garantia formal de fechamento de timing, nem necessariamente reproduzível bit
a bit numa outra placa da mesma peça.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../LICENSE).
