# `run_log`

Rotaciona e replica (tee) toda a saída de console de uma execução num histórico de logs persistente por tipo. `run`/`sim`/`certify` (veja [`orchestrator`](orchestrator.md), [`sim_runner`](sim_runner.md), [`certify`](certify.md)) imprimem muita saída de progresso que, de outro modo, some assim que o terminal rola ou a sessão termina; este módulo escreve tudo também em `<root>/<run_log.logs_dir>/<kind>/latest.log`, de modo que sempre há um alvo de `tail -f` para a execução em andamento, mais um histórico rotacionado de toda execução anterior.

Um `latest.log` antigo de uma execução anterior é arquivado sob o próprio timestamp de início registrado, antes de um novo começar, em vez de ser sobrescrito em silêncio.

## Configuração

| Chave | Significado |
| :--- | :--- |
| `run_log.logs_dir` | Onde o histórico de logs é mantido, relativo à raiz do projeto (padrão `"logs"`). De propósito não fica em `paths.build_dir`, já que o `compile` pode apagar e regenerar o diretório de build à vontade, enquanto o histórico de logs de uma execução vale ser mantido independentemente disso. |

## Pré-requisitos

- `tee` (GNU coreutils).

## Testes

Não há teste automatizado neste repositório. O `tests/test_cli_compile.py` o substitui por uma função vazia nos testes do `spike-run`, porque ele redireciona a saída padrão do processo, e a captura do próprio pytest não consegue compartilhá-la.

## Uso

Não é um subcomando próprio da CLI: é automático em toda invocação de `run`/`sim`/`certify`. Nada a configurar para tê-lo; só o `run_log.logs_dir` vale ser sobrescrito, e só se um projeto quiser o histórico de logs em outro lugar que não o padrão.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
