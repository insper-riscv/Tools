# `sources`

Emite a lista ordenada dos arquivos de um alvo, lida dos manifestos `provides` dos repositórios. As listas de fontes dos `config*.yaml`, do `tests.json` e do projeto do Quartus repetem os mesmos caminhos em vários lugares, e acrescentar um arquivo exigia editar todas. Com o manifesto, cada arquivo é declarado uma vez no repositório que o tem, e este módulo monta a lista de qualquer alvo a partir dele.

## Resolução

O alvo é um componente, escrito como `<repositório>/<componente>`; um nome sem prefixo é um componente do repositório da raiz. A saída traz os componentes de `requires` antes do alvo, em profundidade e na ordem em que o manifesto os lista, e depois os `sources` do próprio componente na ordem declarada. Nenhum arquivo aparece duas vezes, e os caminhos saem relativos à raiz, também para os arquivos de repositórios montados abaixo dela.

Os manifestos lidos são o da própria raiz e os dos repositórios montados abaixo dela: os submódulos do `.gitmodules` e o `src/common`. Um repositório visto duas vezes fica com a primeira pasta encontrada. Os arquivos de um submódulo nunca vêm da listagem de pastas da raiz, só do manifesto do próprio submódulo, e um `requires: <repositório>/<componente>` segue para esse manifesto quando o outro repositório declara `provides`. O formato do manifesto está em [tree_check](tree_check.md).

## Pacote de configuração gerado

O `config_pkg.vhd` do Common-Components é o pacote padrão de constantes, e a plataforma gera outro com o mesmo nome de unidade (ver [memory_map](memory_map.md)). A lista mantém um só arquivo com esse nome, o de um repositório que não é o Common-Components, na posição em que o padrão estaria, de modo que toda unidade que o usa vem depois dele. Sem um gerado na lista, o padrão fica.

## Recursos de placa

O componente pode declarar em `needs` os tipos de recurso de placa de que depende (`block_ram`, `sdram`, `sram`, `nor`, `onchip_flash`, `serial_flash`, `vjtag`). A listagem de arquivos ignora a chave. O validador de placas percorre o mesmo fecho e une os `needs` dos componentes alcançados (ver [board_check](board_check.md)).

## Erros

O comando sai com status 2 e uma linha `sources:` quando um manifesto está malformado, quando o repositório ou o componente de um alvo ou de um `requires` não é encontrado e quando os requisitos formam um ciclo.

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_manifest_sources.py::test_sources_orders_dependencies_first` | Os requisitos de outro repositório vêm antes do alvo. |
| `tests/test_manifest_sources.py::test_sources_rejects_unknown_targets` | Componente, repositório ou manifesto ausente falha. |
| `tests/test_manifest_sources.py::test_the_repository_name_defaults_to_the_folder` | Sem `repository`, a pasta da raiz dá o nome. |
| `tests/test_manifest_sources.py::test_the_subcommand_prints_and_fails` | O comando imprime um caminho por linha e sai com 2 num erro. |
| `tests/test_sources_workspace.py::test_a_top_resolves_requires_across_the_submodules` | Um topo resolve `requires` de Core e Memory, que por sua vez pedem o Common-Components, sem repetir arquivo. |
| `tests/test_sources_config_pkg.py` | O `config_pkg` gerado toma o lugar do padrão, em qualquer ordem de `requires`, e sem ele o padrão fica. |
| `tests/test_sources_workspace.py::test_a_leaf_reaches_the_common_components_at_src_common` | Um repositório que monta o Common-Components em `src/common` o encontra ali. |

## Uso

```bash
uv run riscv-tools --root <repositório> sources core
uv run riscv-tools --root <repositório> sources Core/core Memory/cache
```

Não precisa de `--config`.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
