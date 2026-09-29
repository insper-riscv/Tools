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
símbolo linkável. Escreva os mesmos dois passos à mão, usando o
`memory.mailbox_addr` / `memory.go_flag_addr` do próprio projeto consumidor
(veja o `config.yaml` dele). Exemplo com os valores reais que o
[insper-riscv/Testes](https://github.com/insper-riscv/Testes) configura
(`mailbox_addr=0x3FFC`, `go_flag_addr=0x3FF8`, logo depois do fim da RAM
utilizável); substitua pelos endereços do seu projeto:

```asm
    // mailbox_addr = 1 (PASS) ou 2 (FAIL)
    lui  x15, 0x4
    addi x14, x0, 1            // ou 2 para FAIL
    sw   x14, -4(x15)          // mailbox_addr

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
