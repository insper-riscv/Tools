# `project`

Comandos curtos para trabalhar num projeto criado por `new-project`, sem digitar as opções do `riscv-tools` nem as do Quartus. O projeto lembra a própria placa e a própria plataforma num arquivo `project.yaml`, e um script `rt` na pasta do projeto roda o `riscv-tools` na imagem `dev_tools` com o Quartus do computador.

## O script `rt`

O `new-project` escreve o `rt` na pasta do projeto. Ele monta a pasta do projeto, o Quartus do computador (somente leitura) e a rede do computador no contêiner, e roda o `riscv-tools` lá dentro. Antes disso ele chama o `jtagconfig` do computador, que inicia o `jtagd` que o contêiner alcança pela rede; sem esse servidor o contêiner não enxerga o cabo USB-Blaster.

| Variável | Efeito |
| :--- | :--- |
| `QUARTUS_ROOT` | Pasta onde o Quartus está instalado (padrão `/opt/altera_lite`) |
| `RISCV_TOOLS_HOST` | Nome do computador na trava da placa (padrão `hostname -s`) |
| `RISCV_TOOLS_IMAGE` | Imagem a usar (padrão `ghcr.io/insper-riscv/dev_tools:latest`) |

Qualquer subcomando passa pelo script, por exemplo `./rt project build` ou `./rt profiles --spec ...`. Num daemon do Docker com remapeamento de usuários, o `--network host` é recusado a menos que a execução também use `--userns=host`.

## Uso

```bash
./rt project doctor
./rt project build
./rt project flash Tests/build-de0-cv-64k/arithmetic-add.mif
./rt project help
```

| Ação | O que faz |
| :--- | :--- |
| `doctor` | Confere os arquivos da plataforma, as ferramentas do Quartus no `PATH` e o cabo JTAG; termina com status 1 se faltar um arquivo ou uma ferramenta, e só avisa se não houver cabo |
| `build` | Compila o projeto do Quartus até o passo de `--stop-after` (`map`, `fit` ou `sta`, padrão `sta`), sem gravar a placa |
| `flash ARQUIVO.mif` | Reserva a placa, compila, grava o bitstream e embute o programa, na configuração do `Tests` (`Tests/tools/riscv_build/config.<nome>.yaml`, criada pelo passo 3 do `help`); espera na fila se outra pessoa estiver com a placa |
| `help` | Imprime como rodar os testes e compilar um programa seu, com os endereços desta plataforma |

O comando procura o `project.yaml` na pasta de `--dir` (padrão `.`) e nas pastas acima dela. Não precisa de `--config`.

## O `project.yaml`

| Campo | Conteúdo |
| :--- | :--- |
| `name` | Nome do projeto, como foi digitado |
| `slug` | Identificador derivado do nome; nomeia a pasta, a plataforma e os arquivos |
| `board` | Placa do catálogo |
| `repo` | Pasta do clone do `Insper-RISC-V`, a partir do projeto |
| `platform` | Pasta da plataforma, a partir do clone |

## O help dos testes

A ação `help` explica, na ordem, como baixar o repositório `Tests`, apontá-lo para a plataforma do projeto, gerar a configuração derivada e o cabeçalho do mapa, compilar e rodar os testes existentes e compilar um programa em C seu. Os endereços do cabeçalho do mapa saem do `platform.yaml` do projeto, calculados no momento: o fim da RAM, as palavras do hospedeiro e as duas bancas da FLASH.

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_project.py::test_the_manifest_is_written_and_read_back` | Os quatro campos sobrevivem à gravação |
| `tests/test_project.py::test_the_manifest_is_found_from_a_folder_inside` | A busca sobe de uma subpasta até o projeto |
| `tests/test_project.py::test_a_missing_or_incomplete_manifest_is_an_error` | Sem arquivo ou sem campo, o erro diz o que fazer |
| `tests/test_project.py::test_the_launcher_mounts_the_quartus_and_shares_the_network` | O script é executável, é shell válido e empresta o Quartus e a rede |
| `tests/test_project.py::test_build_stops_after_the_chosen_quartus_step` | O comando é `program --stop-after` na configuração da plataforma |
| `tests/test_project.py::test_flash_holds_the_lock_of_the_board` | O programa roda dentro de `board lock --wait` na mesma placa, na configuração do Tests |
| `tests/test_project.py::test_flash_needs_the_tests_to_be_prepared` | Sem a configuração do Tests, o erro manda preparar o Tests |
| `tests/test_project.py::test_the_cable_is_found_by_the_idcode_of_the_board` | O cabo é achado pelo IDCODE da placa, mesmo com várias placas no computador |
| `tests/test_project.py::test_the_idcode_comes_from_the_board_catalog` | O IDCODE vem da cadeia JTAG do catálogo |
| `tests/test_project.py::test_the_launcher_takes_the_same_lock_as_the_host` | O `rt` compartilha o `/tmp` e o nome do computador, para pegar a mesma trava |
| `tests/test_project.py::test_the_files_of_the_platform_are_checked` | Arquivo ausente reprova com o conselho |
| `tests/test_project.py::test_the_quartus_tools_are_looked_up_on_the_path` | Ferramenta ausente reprova e indica o `./rt` |
| `tests/test_project.py::test_a_missing_cable_is_a_warning_not_a_failure` | A falta de cabo só avisa |
| `tests/test_project.py::test_the_header_constants_follow_the_platform` | Os valores do cabeçalho vêm do mapa |
| `tests/test_project.py::test_the_tests_help_names_the_project_and_the_program` | O help usa os nomes do projeto nos dois idiomas |
| `tests/test_project.py::test_the_project_command_runs_build_in_the_checkout` | O `build` roda no clone com a configuração certa |
| `tests/test_project.py::test_flash_without_an_image_exits_with_status_one` | O `flash` exige o `.mif` |
| `tests/test_project.py::test_the_project_command_needs_a_project` | Fora de um projeto, o erro indica o `new-project` |
| `tests/test_project.py::test_the_project_command_prints_the_tests_help` | O `help` imprime os valores da plataforma |
| `tests/test_new_project.py::test_the_command_writes_the_manifest_and_the_launcher` | O `new-project` grava o `project.yaml` e o `rt` |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
