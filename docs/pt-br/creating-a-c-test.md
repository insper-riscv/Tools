# Criando um teste RISC-V em C

## Onde ele fica

Crie uma pasta em `paths.c_dir` do projeto consumidor (normalmente `c/`),
com o nome do que o teste faz, contendo um `src.c`:

```
c/
└── example-add/
    └── src.c
```

O `riscv-tools compile` encontra automaticamente toda pasta
`<c_dir>/<name>/src.c`: o nome da pasta vira o nome do teste no manifest; não
há mais nada a registrar.

## Comentários de cabeçalho

Três comentários `//` opcionais no topo do `src.c` configuram como o
[`compiler`](modules/compiler.md) compila e roda o teste:

| Cabeçalho | Significado |
| :--- | :--- |
| `RV32_EXT: M` | Extensões ACRESCENTADAS à base `rv32i` implícita. Separadas por vírgula; a ordem não importa (`M,A` e `A,M` viram `rv32ima`). |
| `RV32_TEST_KIND: unit` | Padrão se omitido. Verificado só pelo mailbox PASS/FAIL. Compila para hardware real e para sim. Veja [testes `unit` versus `memory`](#testes-unit-versus-memory) abaixo. |
| `RV32_TEST_KIND: memory` | Um teste `unit` expandido: além disso, um global `results` é comparado com o golden.json depois que o mailbox lê PASS. Veja [testes `unit` versus `memory`](#testes-unit-versus-memory) abaixo. |
| `RV32_TIMEOUT_S: 5` | Só para testes reais: quanto o orchestrator espera o mailbox deste teste antes de recorrer a uma reprogramação completa com nova tentativa. O padrão é `quartus.default_timeout_s`. Mantenha baixo para testes unit simples; dê mais tempo aos testes lentos ou de memória. |

```c
// RV32_EXT: M
// RV32_TEST_KIND: memory
// RV32_TIMEOUT_S: 5
```

## Escrevendo o teste

```c
// c/example-mem/src.c
#include "rv32_test.h"

int main(void) {
    volatile unsigned int *buf = (volatile unsigned int *)0x10;
    buf[0] = 0x11111111;

    if (buf[0] == 0x11111111) {
        RV32_PASS();
    } else {
        RV32_FAIL();
    }
}
```

O `rv32_test.h` é gerado a partir do `memory.mailbox_addr` do seu
`config.yaml`: não o escreva à mão; gere (ou gere de novo, depois de mudar esse
endereço) com:

```bash
uv run riscv-tools --config <project>/config.yaml generate-header
```

Escreve em `<paths.include_dir>/rv32_test.h` por padrão (`--out` para
sobrescrever). A própria `rv32_wait_restart` continua vindo do `crt0.S` do seu
projeto: este pacote só cuida do lado do mailbox.

Evite `(volatile unsigned int *)0x0`: o GCC trata um ponteiro nulo literal como
comportamento indefinido e pode otimizar o acesso inteiro para fora,
independentemente do `volatile`. Escolha um endereço diferente de zero para
qualquer coisa no começo da RAM/ROM.

## Testes `unit` versus `memory`

`memory` é `unit` expandido, e não um tipo separado e sem relação: pegue
qualquer teste `unit` que funcione, adicione um global `results` em que ele
escreve a resposta, troque o comentário de cabeçalho para `memory`, e ele agora
é um teste `memory`. Nada na lógica de `RV32_PASS()`/`RV32_FAIL()` muda.

- `unit` (o padrão): passar significa o mailbox ler PASS. Basta quando o teste
  consegue se julgar por inteiro com um `if`. Compila tanto para
  `compile --emit mif` (real) quanto para `--emit hex` (sim).
- `memory`: PASS no mailbox, **e depois** um global `results` é comparado com o
  golden.json, tanto no hardware real (um dump da RAM por JTAG) quanto na sim
  (a mesma checagem, feita ao vivo pelo barramento de escrita da RAM, já que a
  sim não tem como fazer dump de um array de memória diretamente; veja o
  `sim/test_c_program.py` do próprio projeto). Um teste que sinaliza FAIL, ou
  estoura o timeout, nunca chega a essa segunda checagem, igual a um teste
  `unit` que falha do mesmo jeito. É isso que pega um teste que chegou a
  `RV32_PASS()` com um valor calculado errado (por exemplo uma soma que saiu
  com erro de um): só o mailbox não distingue "rodou até o fim" de "rodou até o
  fim e errou a resposta".

  Diferente de um teste de memória em asm (veja
  [creating-an-asm-test.md](creating-an-asm-test.md)), um teste de memória em C
  **não traz golden.json versionado**: declare um global `results`:

  ```c
  // RV32_TEST_KIND: memory
  #include "rv32_test.h"

  volatile unsigned int results[3];

  int main(void) {
      results[0] = ...;
      results[1] = ...;
      results[2] = ...;
      RV32_PASS();
  }
  ```

  Na compilação (tanto `--emit mif` quanto `--emit hex`), o golden é gerado
  automaticamente: o endereço e o tamanho de `results` são resolvidos pela
  tabela de símbolos do ELF compilado (`nm -S`, o mesmo mecanismo do
  `generate-golden --symbol`), o ELF roda no Spike (veja
  [golden_generator](modules/golden_generator.md)), e um
  `<build_dir>/<name>.golden.json` novo é escrito, nunca um arquivo que você
  escreve ou versiona. A correção é validada como "a CPU deste projeto produz o
  mesmo conteúdo de memória que o Spike produz para o mesmo programa", e não
  contra um valor que alguém calculou à mão uma vez e que pode ficar defasado
  em silêncio depois de uma edição. Exige o Spike no `PATH` (veja
  [generating-a-golden.md](generating-a-golden.md) para a mecânica, se você
  quiser rodar o Spike à mão, por exemplo para depurar uma divergência).

  `results` pode guardar o que o teste quiser conferir (valores simples, uma
  struct pequena, um array); o único requisito é ser um global real e com
  tamanho (`volatile`, para o compilador não otimizar as escritas para fora),
  e não um ponteiro cru para um endereço fixo.

  Tanto `compile --emit mif` (real) quanto `--emit hex` (sim) compilam e
  verificam por completo um teste `memory` agora: a comparação do golden com o
  Spike roda igual nos dois, então um valor calculado errado é pego na suíte
  rápida de GHDL a cada push, e não só quando roda de verdade.

## Compilando, inspecionando, rodando

```bash
uv run riscv-tools --config <project>/config.yaml compile --emit mif   # real/FPGA, todos os testes
uv run riscv-tools --config <project>/config.yaml compile --emit hex   # sim, todos os testes
uv run riscv-tools --config <project>/config.yaml compile --emit asm   # inspecionar o codegen (gcc -S)
uv run riscv-tools --config <project>/config.yaml run                  # suíte de hardware real
uv run riscv-tools --config <project>/config.yaml sim                  # suíte de sim (cocotb/GHDL)
```

Veja [creating-an-asm-test.md](creating-an-asm-test.md) para escrever um teste
direto em assembly RISC-V: por exemplo, para fixar um modo de endereçamento
exato que um compilador pode não escolher sozinho.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../LICENSE).
