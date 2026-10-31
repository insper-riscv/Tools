# Criando um teste RISC-V em assembly

Útil quando você precisa fixar uma sequência de instruções ou um modo de
endereçamento exato que um compilador é livre para evitar: por exemplo,
provar se `x0` como registrador base de load/store com um imediato grande se
comporta corretamente, algo que o GCC pode ou não emitir para uma expressão C
equivalente.

## Onde ele fica

Uma pasta em `paths.asm_dir` (normalmente `asm/`), com o nome do que o teste
faz, contendo um `src.S`:

```
asm/
└── section6-loadstore/
    └── src.S
```

Mesma convenção dos testes em C (veja
[creating-a-c-test.md](creating-a-c-test.md#onde-ele-fica)): só
`asm_dir`/`src.S` em vez de `c_dir`/`src.c`.

## Comentários de cabeçalho

Convenção idêntica à dos testes em C (`RV32_EXT`, `RV32_TEST_KIND`,
`RV32_TIMEOUT_S`), escrita como comentários `//` (o `as` do GNU aceita
comentários de linha no estilo C++, não só `#`/`;`). Veja
[creating-a-c-test.md](creating-a-c-test.md#comentários-de-cabeçalho) para a
referência completa.

## Ponto de entrada

O `crt0.S` (no projeto consumidor) chama um símbolo chamado `main` depois de
preparar `.data`/`.bss`: o seu arquivo `.S` precisa definir exatamente esse
símbolo:

```asm
    .section .text
    .globl main
main:
    ...
```

## Sinalizando PASS/FAIL

`RV32_PASS()`/`RV32_FAIL()` do `rv32_test.h` são funções C `static inline`,
então um arquivo `.S` separado não consegue dar `call` nelas: não existe
símbolo linkável. Use as macros `RVMODEL_HALT_PASS` e
`RVMODEL_HALT_FAIL(código)` do `rv32_platform.h` do projeto (os mesmos nomes do
modelo do riscv-arch-test), que escrevem o `tohost` (`1` para PASS,
`(código << 1) | 1` para FAIL) e saltam para `rv32_wait_restart`. Elas usam
`t0` e `t1`.

```asm
    RVMODEL_HALT_PASS          // ou RVMODEL_HALT_FAIL(3)
```

Sem as macros, os mesmos passos à mão são:

```asm
    li   t0, RV32_TOHOST       // memory.tohost_addr do projeto
    li   t1, 1                 // (código << 1) | 1 para FAIL
    sw   t1, 0(t0)
    sw   x0, 4(t0)

    // Volta para o loop de reinício do crt0.S: NÃO é um spin infinito.
    // É isso que permite ao orchestrator recarregar por JTAG o próximo
    // teste no mesmo bitstream já programado (veja rv32_wait_restart no
    // crt0.S), em vez de exigir uma recompilação + reprogramação
    // completas depois de cada teste.
    j rv32_wait_restart
```

Terminar num loop de spin próprio `1: j 1b` em vez de `j rv32_wait_restart`
faz a suíte inteira travar no *próximo* teste: o núcleo nunca volta ao estado
de onde o orchestrator espera recarregá-lo por JTAG.

## Exemplo completo

Veja [asm/section6-loadstore/src.S no insper-riscv/Testes](https://github.com/insper-riscv/Testes/blob/main/asm/section6-loadstore/src.S)
para um exemplo completo (carrega um registrador base, faz um ciclo
LUI+SW+LW, e então sinaliza PASS como acima).

## Compilando, inspecionando, rodando

Mesma CLI dos testes em C:

```bash
uv run riscv-tools --config <project>/config.yaml compile --emit mif   # todos os testes, real
uv run riscv-tools --config <project>/config.yaml compile --emit hex   # todos os testes, sim
uv run riscv-tools --config <project>/config.yaml run                  # suíte de hardware real
uv run riscv-tools --config <project>/config.yaml sim                  # suíte de sim (cocotb/GHDL)
```

`compile --emit asm` só repassa os arquivos `.S` sem alterá-los: eles já são
assembly, não há o que compilar.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../LICENSE).
