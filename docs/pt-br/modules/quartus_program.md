# `quartus_program`

O caminho lento, "base": um `quartus_sh --flow compile` completo seguido de `quartus_pgm`, ou um atalho só de reprogramação quando o bitstream não mudou. Feito para rodar uma vez no início, para estabelecer um bitstream de base, e de novo como fallback se um teste recarregado por JTAG (veja [`rom_writer`](rom_writer.md), [`htif`](htif.md)) estoura o timeout, caso a própria placa tenha travado em vez de o teste ter travado.

## 1. Dois pontos de entrada

| Função | O que faz | Custo |
| :--- | :--- | :--- |
| `full_reconfigure` | Embute um `.mif` como o `init_file` da ROM, compila o projeto Quartus inteiro e depois programa a placa. | Minutos (síntese completa). |
| `program_only` | Reprograma a partir de um `.sof` já gerado, sem recompilar. | Segundos. Só é seguro se o fonte VHDL não mudou desde que esse `.sof` foi gerado. |

O `full_reconfigure` sempre chama os passos de compilação e programação juntos numa única cadeia `bash -c`, nunca como duas chamadas Python separadas de subprocesso: invocar o `quartus_pgm` como subprocesso próprio logo depois do `quartus_sh` já se observou quebrar a chain JTAG (`Error 213019: Can't scan JTAG chain`), enquanto encadear os mesmos dois comandos dentro de um único processo de shell não quebra.

## 2. Opções da compilação

O `program` aceita, além do `.mif`, as opções abaixo. Sem nenhuma delas o fluxo é o de sempre: `quartus_sh --flow compile` seguido de `quartus_pgm`. Com `--seed`, `--generic` ou `--stop-after`, a compilação passa pelo script único `tcl/compile.tcl`, que substitui os `<projeto>_synth.tcl` de cada plataforma.

| Opção | Efeito |
| :--- | :--- |
| `--seed N` | Semente do posicionamento (padrão do script, 5); o script também fixa o modo `HIGH PERFORMANCE EFFORT` |
| `--generic NOME=VALOR` | Troca um generic inteiro do topo só nesta compilação, sem gravar no `.qsf`; repetível |
| `--stop-after map\|fit\|sta` | Para depois da síntese, do ajuste ou da análise de tempo; não programa a placa |
| `--compile-only` | Compila o fluxo inteiro e não programa a placa |
| `--board NOME` (global) | Escolhe o cabo pelo IDCODE do FPGA da placa, pela seleção de placas do `jtag_link` |
| `--project-dir`, `--project-name` | Projeto Quartus no lugar de `quartus.project_dir` e `quartus.project_name`, para um projeto escrito por `board generate`; o `.sof` é `output_files/<nome>.sof` |

O `.mif` só é obrigatório quando a placa é programada. Com `--compile-only` ou `--stop-after`, nenhum cabo é consultado.

| Ponto de parada | Estágios executados |
| :--- | :--- |
| `map` | Síntese |
| `fit` | Síntese e ajuste |
| `sta` | Síntese, ajuste e análise de tempo |
| completo | `execute_flow -compile` |

## 3. Configuração

| Chave | Significado |
| :--- | :--- |
| `quartus.project_dir` | Caminho do diretório do projeto Quartus. Sem padrão; específico do projeto. |
| `quartus.project_name` | Nome do projeto/revisão do Quartus passado ao `quartus_sh --flow compile`. Sem padrão. |
| `quartus.sof_file` | Caminho (relativo a `project_dir`) do `.sof` compilado. Sem padrão. |
| `quartus.rom_mif_target` | Caminho (relativo a `project_dir`) de onde a megafunção da ROM lê o `init_file` na compilação. Sem padrão. |
| `quartus.stale_cache_dirs` | Diretórios apagados antes de toda compilação (padrão `["db", "incremental_db", "output_files", "simulation"]`), já que o `init_file` de uma megafunção de ROM é um parâmetro string que o próprio cache de build incremental do Quartus não rastreia como fonte do projeto. |

## 4. Pré-requisitos

- O Quartus Prime Lite no `PATH` (`quartus_sh`, `quartus_pgm`), instalado como no `QUARTUS_INSTALL.md` do Infra, um projeto Quartus e uma placa conectada por JTAG.

## 5. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_program_options.py` | O `compile.tcl` registra as mesmas chamadas do `de0-cv_synth.tcl`, a cadeia de compilação e programação, o `program_only` contra o `de0-cv_program.sh` e o `cmd_program` com as opções novas |

Os scripts antigos ficam como fixtures dos testes (`tests/fixtures/multifpga/handwritten/`), executados em `tclsh` com os comandos do Quartus substituídos por registros.

## 6. Uso

```bash
uv run riscv-tools --config /path/to/project/config.yaml program <path-to.mif>
```

Também é chamado internamente pelo [`orchestrator`](orchestrator.md) como o passo inicial de reconfiguração de uma rodada completa da suíte, e como o seu próprio nível de recuperação automática quando o `tohost` de um teste recarregado por JTAG nunca muda.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
