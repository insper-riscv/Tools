# `quartus_program`

O caminho lento, "base": um `quartus_sh --flow compile` completo seguido de `quartus_pgm`, ou um atalho só de reprogramação quando o bitstream não mudou. Feito para rodar uma vez no início, para estabelecer um bitstream de base, e de novo como fallback se um teste recarregado por JTAG (veja [`rom_writer`](rom_writer.md), [`mailbox`](mailbox.md)) estoura o timeout, caso a própria placa tenha travado em vez de o teste ter travado.

## Dois pontos de entrada

| Função | O que faz | Custo |
| :--- | :--- | :--- |
| `full_reconfigure` | Embute um `.mif` como o `init_file` da ROM, compila o projeto Quartus inteiro e depois programa a placa. | Minutos (síntese completa). |
| `program_only` | Reprograma a partir de um `.sof` já gerado, sem recompilar. | Segundos. Só é seguro se o fonte VHDL não mudou desde que esse `.sof` foi gerado. |

O `full_reconfigure` sempre chama os passos de compilação e programação juntos numa única cadeia `bash -c`, nunca como duas chamadas Python separadas de subprocesso: invocar o `quartus_pgm` como subprocesso próprio logo depois do `quartus_sh` já se observou quebrar a chain JTAG (`Error 213019: Can't scan JTAG chain`), enquanto encadear os mesmos dois comandos dentro de um único processo de shell não quebra.

## Configuração

| Chave | Significado |
| :--- | :--- |
| `quartus.project_dir` | Caminho do diretório do projeto Quartus. Sem padrão; específico do projeto. |
| `quartus.project_name` | Nome do projeto/revisão do Quartus passado ao `quartus_sh --flow compile`. Sem padrão. |
| `quartus.sof_file` | Caminho (relativo a `project_dir`) do `.sof` compilado. Sem padrão. |
| `quartus.rom_mif_target` | Caminho (relativo a `project_dir`) de onde a megafunção da ROM lê o `init_file` na compilação. Sem padrão. |
| `quartus.stale_cache_dirs` | Diretórios apagados antes de toda compilação (padrão `["db", "incremental_db", "output_files", "simulation"]`), já que o `init_file` de uma megafunção de ROM é um parâmetro string que o próprio cache de build incremental do Quartus não rastreia como fonte do projeto. |

## Pré-requisitos

- O Quartus Prime Lite no `PATH` (`quartus_sh`, `quartus_pgm`), instalado como no `QUARTUS_INSTALL.md` do Infra, um projeto Quartus e uma placa conectada por JTAG.

## Testes

Não há teste automatizado neste repositório. Um runner self-hosted preparado como no `RUNNER_SETUP.md` do Infra roda a suíte de hardware real de um projeto consumidor (`riscv-tools run`), que é o único lugar onde este módulo é exercitado.

## Uso

```bash
uv run riscv-tools --config /path/to/project/config.yaml program <path-to.mif>
```

Também é chamado internamente pelo [`orchestrator`](orchestrator.md) como o passo inicial de reconfiguração de uma rodada completa da suíte, e como o seu próprio nível de recuperação automática quando o mailbox de um teste recarregado por JTAG nunca responde.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
