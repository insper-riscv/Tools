# `bin_to_image`

Converte um `.bin` plano já compilado em formatos que o hardware ou a simulação conseguem carregar.

## O que produz

| Formato | Função | Usado por |
| :--- | :--- | :--- |
| `.mif` (Intel/Altera Memory Initialization File) | `bin_to_mif` | Hardware real: embutido num projeto Quartus como o `init_file` de uma instância de ROM/RAM, ou gravado por JTAG pelo [`rom_writer`](rom_writer.md). |
| `.hex` (texto simples, uma palavra de 32 bits por linha; o padrão `sim.hex_format: words`) | `bin_to_hex` | Simulação: carregado pelo testbench VHDL do [`sim_runner`](sim_runner.md) e pela execução do Spike do [`golden_generator`](golden_generator.md). |

Os dois completam o binário com palavras zero até uma profundidade de palavras fixa (o tamanho de memória do projeto), então um programa menor que a memória de destino ainda produz uma imagem com a profundidade completa.

## Configuração

Nenhuma: recebe o caminho do binário, o caminho de saída e a profundidade em palavras como argumentos diretos de quem o chama; não tem seção própria no `config.yaml`.

## Testes

Não há teste dedicado. Ele é exercitado pelo `compile`:

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_cli_compile.py::test_cmd_compile_mif_builds_every_kind` | O `.mif` de cada teste é escrito a partir do binário compilado. |
| `tests/test_cli_compile.py::test_cmd_compile_hex_builds_every_kind` | O `.hex` de cada teste é escrito a partir do binário compilado. |

## Uso

Não é um subcomando próprio da CLI: é chamado internamente por `compile --emit mif` e `compile --emit hex` (veja o [README](../../../README.md#uso) principal) logo depois de o [`compiler`](compiler.md) produzir o `.bin`.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
