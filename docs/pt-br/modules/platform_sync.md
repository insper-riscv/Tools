# `platform_sync`

Escreve o `config.yaml` de uma plataforma para o projeto que a consome. Uma plataforma guarda os caminhos do `config.yaml` a partir da raiz do repositório que a tem, mas o projeto que roda testes nela (Tests, Certification) tem esse repositório como submódulo, e os mesmos caminhos começam uma pasta mais fundo. Escrever o prefixo à mão em cada config faz o caminho de um arquivo mudar em dezenas de lugares quando a plataforma se reorganiza. Este módulo resolve a cadeia `extends:` da plataforma, põe a pasta do submódulo na frente de cada caminho que ela possui e escreve um arquivo completo, que o config de variante do consumidor estende.

## Chaves que ganham o prefixo

| Chave | Conteúdo |
| :--- | :--- |
| `toolchain.specs` | Arquivo de specs do GCC da plataforma |
| `paths.boot_memory`, `paths.boot_memory_linker_script` | Fonte e linker script da BOOT_MEMORY |
| `paths.sources`, `emulator.sources` | Fontes C e assembly do runtime e do substituto do Spike |
| `freq_sweep.pll_file` | Fonte da PLL que a varredura de frequência reescreve |
| `quartus.project_dir` | Pasta do projeto do Quartus |
| `sim.vhdl_sources`, `sim.python_path` | Fontes VHDL do topo de simulação e pasta do testbench |

Os caminhos do consumidor (`paths.include_dir`, `paths.build_dir`, `paths.c_dir` e `paths.asm_dir`) e os nomes (`quartus.project_name`) ficam como estão. Um caminho absoluto também.

## Uso

```bash
uv run riscv-tools --root <consumidor> platform sync \
  --source Insper-RISC-V/src/cyclone-v/de0-cv/config.yaml \
  --prefix Insper-RISC-V \
  --output tools/riscv_build/config.de0-cv.yaml
```

O arquivo escrito começa com um cabeçalho que diz que é gerado e de onde veio. Um config de variante do consumidor passa a dizer `extends: config.de0-cv.yaml` e acrescenta só os próprios caminhos.

Com `--check` nada é escrito, e o comando termina com status 1 quando o arquivo falta ou difere do que seria escrito. É o passo de CI que impede ninguém de editar o arquivo à mão ou de esquecer de regerá-lo depois que a plataforma muda.

Não precisa de `--config`.

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_platform_sync.py::test_flatten_resolves_the_extends_chain` | A cadeia `extends:` da plataforma é resolvida |
| `tests/test_platform_sync.py::test_rebase_prefixes_every_path_the_platform_owns` | Textos e listas de caminhos ganham o prefixo |
| `tests/test_platform_sync.py::test_rebase_leaves_the_consumers_paths_and_other_keys` | Os caminhos do consumidor e os nomes ficam como estão |
| `tests/test_platform_sync.py::test_rebase_keeps_an_absolute_path_and_does_not_mutate` | Um caminho absoluto fica igual e a entrada não muda |
| `tests/test_platform_sync.py::test_sync_then_check_passes_and_a_change_fails` | O arquivo escrito passa em `--check` até a plataforma mudar |
| `tests/test_platform_sync.py::test_command_runs_through_the_cli_without_config` | O comando roda sem `--config` |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
