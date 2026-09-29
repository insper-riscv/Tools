# Gerando um golden JSON pelo Spike

## Requisitos

Spike e a toolchain GCC RISC-V (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`)
no `PATH`, instalados como descrito no
[insper-riscv/Infra](https://github.com/insper-riscv/Infra)
(`GCC_SETUP.md` e `SPIKE_SETUP.md`). Este pacote não compila nenhum dos dois.

O Spike precisa manter o módulo de debug longe do endereço 0, o que o build do
Infra faz. Sem isso, o Spike aborta na inicialização com `devices at [0, 1000)
and [0, 10000) overlap` para qualquer alvo cuja ROM começa no endereço 0. O
`generate-golden` faz uma sondagem única disso antes da primeira execução do
Spike e para com uma indicação do `SPIKE_SETUP.md` quando ela falha.

Um teste `RV32_TEST_KIND: memory` precisa de um golden JSON: o valor de byte
esperado em cada endereço que o [`mem_validator`](modules/mem_validator.md)
confere depois que o teste roda (veja
[creating-a-c-test.md](creating-a-c-test.md#testes-unit-versus-memory)). Em vez
de calcular esses valores à mão, o `golden_generator` roda o teste compilado no
Spike (o simulador de referência RISC-V) e os lê de volta do dump de memória
dele.

## Como funciona

O `crt0.S`/`link.ld` do seu projeto definem `tohost`/`fromhost` (HTIF:
Host-Target InterFace, a convenção padrão que o Spike/`riscv-tests` usam) e
traduzem o valor PASS/FAIL do mailbox em uma escrita em `tohost` quando o teste
termina (veja a seção de HTIF na doc do seu projeto, ou
[creating-an-asm-test.md](creating-an-asm-test.md) se você escreve o teste em
assembly).

O `generate-golden` segue estes passos:

1. Resolve o ponto de entrada e o `tohost` pela tabela de símbolos do ELF
   compilado (`nm`).
2. Copia o ELF e, com `objcopy --add-symbol`, define `begin_signature` e
   `end_signature` no intervalo pedido, mais `fromhost` logo depois de
   `tohost` quando o link script não o define (o Spike ignora o `tohost` sem
   ele) e um alias `tohost` quando `emulator.tohost_symbol` usa outro nome. O
   ELF original não é alterado.
3. Roda `spike --isa=... -m<regiões> --disable-dtb --pc=<entrada>
   +signature=<arquivo> +signature-granularity=4` sobre a cópia. O Spike roda
   até o teste escrever um valor diferente de zero em `tohost`, tenha ele
   passado ou falhado, termina, e escreve o intervalo como uma palavra de 32
   bits por linha.
4. Converte as palavras em `{byte_address: byte_value}`, em little-endian,
   deslocado para ficar relativo à RAM.

A etapa é limitada por `emulator.timeout_s`: um teste que nunca escreve
`tohost` faz a geração falhar em vez de travá-la.

Isso nunca toca o hardware real: é uma simulação de software completa, útil
justamente por ser rápida e não precisar de uma placa nem de um cabo JTAG
conectado.

## Gerando um golden JSON

```bash
uv run riscv-tools --config <project>/config.yaml compile --emit mif   # produz o .elf

uv run riscv-tools --config <project>/config.yaml generate-golden \
    build/real/my_test.elf \
    --march rv32im \
    --start 0x10 --end 0x20 \
    --out c/my_test/golden.json
```

- `--march` deve combinar com o march do próprio teste (o cabeçalho `RV32_EXT`,
  resolvido do mesmo jeito que o `compile` o resolve: veja
  [creating-a-c-test.md](creating-a-c-test.md#comentários-de-cabeçalho)).
- `--start`/`--end` são endereços de byte (hex ou decimal funcionam): o
  intervalo semiaberto `[start, end)` a capturar, arredondado para palavras
  inteiras de 32 bits.
- `--out` é onde o golden JSON é escrito, no formato exato que o
  [`mem_validator`](modules/mem_validator.md) espera.

O arquivo resultante é um mapa JSON simples `{endereço de byte em hex: valor de
byte inteiro}`, seguro para versionar e para editar à mão depois, se precisar
(por exemplo, para relaxar uma checagem de propósito).

## Verificando que funciona no seu setup

`tests/test_generate_golden.py` (no repositório deste pacote) é um teste de
ponta a ponta de todo esse caminho: ele compila dois programas de fixture
minúsculos (um em C, um em asm escrito à mão; veja `tests/fixtures/htif_min/`),
passa cada um pelo `generate_golden` no Spike instalado, e confere que os bytes
devolvidos estão exatamente certos, inclusive a ordem little-endian. Rode você
mesmo para confirmar que o seu Spike funciona antes de confiar num golden que
ele produza:

```bash
uv sync --group dev
uv run pytest tests/test_generate_golden.py -v
```

Ele é pulado automaticamente (não falha) se o `spike` ou a toolchain GCC
RISC-V não estiverem disponíveis.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../LICENSE).
