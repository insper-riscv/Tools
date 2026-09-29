# `c_to_asm`

Compila um único fonte C direto para assembly RISC-V legível (`gcc -S`), para inspecionar ou depurar a geração de código. Um fonte `.S` já é assembly e é copiado sem alterações, em vez de ser reprocessado.

## Configuração

Compartilha as mesmas configurações de toolchain/ISA do [`compiler`](compiler.md) (`toolchain.gcc`, `isa.base`, `isa.canonical_order`), já que é o mesmo compilador e a mesma convenção do cabeçalho `RV32_EXT`, só com outro formato de saída.

## Pré-requisitos

- A toolchain GCC RISC-V (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) no `PATH`, instalada como no `GCC_SETUP.md` do [insper-riscv/Infra](https://github.com/insper-riscv/Infra).

## Testes

Não há teste automatizado neste repositório. O `compile --emit asm` não é coberto por um teste aqui; um projeto pode conferir a saída à mão.

## Uso

```bash
uv run riscv-tools --config /path/to/project/config.yaml compile --emit asm
```

Escreve um arquivo `.s` por teste descoberto, junto com a saída normal de `.mif`/`.hex`, para ser lido e não executado.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
