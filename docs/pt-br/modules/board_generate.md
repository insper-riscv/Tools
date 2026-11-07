# `board_generate`

Compõe os geradores no projeto Quartus de uma plataforma numa placa (`riscv-tools board generate`).

## 1. Função

Chama cada gerador e junta o texto, sem escrever conteúdo próprio. A pasta de saída é de construção e não é versionada.

## 2. Arquivos gerados

| Arquivo | Gerador |
| :--- | :--- |
| `<plataforma>_<placa>_top.vhd` | `top_generator` |
| `<plataforma>_<placa>_pll.v` | `pll_generator` |
| `<plataforma>_<placa>.sdc` | `sdc_generator` |
| `<plataforma>_<placa>.qpf` e `.qsf` | `quartus_project`, com os pinos de `pin_assignments` |
| `chip_<chip>_pkg.vhd` | `chip_package`, um por chip da placa |

O projeto fica em `<saída>/<plataforma>-<placa>/`. O comando de compilação é o `program` (ver [quartus_program](quartus_program.md)).

## 3. Uso

```bash
uv run riscv-tools --root <espaço de trabalho> board generate \
    --platform <plataforma>.yaml --board de0-cv --out build \
    --target de0_cv_map --target soc --target Memory/flash_chip
```

| Opção | Efeito |
| :--- | :--- |
| `--board` (global) | Placa; sem ela vale o campo `board` ou a única entrada de `boards` |
| `--boards-dir`, `--chips-dir` | Padrões `<raiz>/boards` e `<raiz>/Memory/chips` |
| `--target` | Componente cujo fecho de fontes entra no `.qsf`; repetível |
| `--seed` | Semente do `.qsf`, padrão 5 |
| `--accept-inferred-pins` | Aceita construir com pino `inferred` |
| `--hand-qsf`, `--hand-sdc`, `--hand-pll`, `--ignore-source` | Imprimem o relatório de [board_equivalence](board_equivalence.md) contra os arquivos escritos à mão |

Os avisos (fase do `DRAM_CLK` não medida, papel opcional ausente, backend sem entidade) saem em `stderr`. Sai com status 2 quando uma entrada é inválida, e com status 1 quando o relatório de equivalência acha uma perda.

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_generate.py` | Arquivos das seis placas (as de `altpll` com um escritor de teste), `.qsf`, determinismo e escrita |
| `tests/test_board_generate_cli.py` | O comando escreve a pasta, imprime o relatório e sai com 2 numa entrada inválida |
| `tests/test_generator_uniqueness.py` | Cada tipo de texto gerado tem um só módulo escritor |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
