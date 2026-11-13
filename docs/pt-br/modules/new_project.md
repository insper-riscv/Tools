# `new_project`

Cria um projeto para uma placa conhecida. Dentro da imagem `dev_tools`, um único comando baixa o repositório `Insper-RISC-V` com os submódulos, copia a plataforma da placa com o nome novo, escreve o `platform.yaml` a partir das escolhas, registra a plataforma no repositório, gera os arquivos que dela decorrem e imprime um help curto com as dicas para mudar o projeto.

## Uso

```bash
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/w/.home \
  -v "$PWD":/w -w /w ghcr.io/insper-riscv/dev_tools:latest \
  riscv-tools new-project --new "de0-cv-64k" --board de0-cv \
  --profile rv32im_zicclsm_zicntr_zihpm \
  --rom 64K --ram 64K --icache 32768 --dcache 32768
```

O projeto fica em `./de0-cv-64k/Insper-RISC-V`, dentro da pasta montada, e continua depois que o contêiner termina. Um nome como `--new "Meu Projeto de Teste"` fica em `./meu-projeto-de-teste/Insper-RISC-V`. Não precisa de `--config`.

## Opções

| Opção | Efeito |
| :--- | :--- |
| `--new` | Nome do projeto, obrigatório: letras (maiúsculas e minúsculas, com acentos), dígitos, espaços, hifens e sublinhados; vazio, só espaços ou qualquer outro caractere é recusado |
| `--board` | Placa do catálogo (`boards/`); uma placa desconhecida é recusada com a lista das conhecidas |
| `--profile` | Perfil do núcleo; sem a opção, vale o da plataforma de partida |
| `--rom`, `--ram` | Tamanho da região de FLASH e da RAM, como `64K` ou `1M` |
| `--icache`, `--dcache` | Tamanho da cache em bits, ou `off` |
| `--dir` | Pasta onde o projeto é criado (padrão `.`) |
| `--source` | Endereço do repositório `Insper-RISC-V` a baixar |
| `--repo` | Usa um clone existente em vez de baixar um |
| `--no-generate` | Escreve a plataforma e não gera os arquivos que decorrem dela |
| `--lang` | Idioma do help impresso, `pt` ou `en` (padrão `pt`) |

Uma opção de memória que não é dada mantém o valor da plataforma de partida.

## O que o comando faz

1. Baixa o repositório com os submódulos, ou usa o clone de `--repo`.
2. Confere o nome (e deriva o identificador), a placa, o perfil e os tamanhos. O perfil precisa estar entre os que `Core/profiles/matrix.yaml` expande e ter Zifencei quando a BOOT_MEMORY da partida executa `fence.i` (sem a extensão a instrução é ilegal e o boot reinicia para sempre), a ROM precisa ser múltiplo de dois setores de 4 KiB (duas bancas) e a RAM múltiplo de 4 KiB.
3. Escolhe a plataforma de partida, a única fora de `calibration/` que lista a placa e tem `top`.
4. Calcula o novo `platform.yaml` e as edições do `paths.yaml` antes de escrever qualquer coisa, de modo que um repositório fora do formato esperado não recebe uma pasta pela metade.
5. Copia a pasta da plataforma, renomeia arquivos e nomes VHDL e dá ao topo de simulação uma entidade própria.
6. Escreve o `platform.yaml` e registra a plataforma no `paths.yaml` (lista de plataformas e os componentes do mapa, do topo da placa e do topo de simulação) e no script de listas de fontes.
7. Gera o mapa de memória, as listas de fontes, confere o mapa e escreve o projeto do Quartus.
8. Escreve na pasta do projeto o `project.yaml`, o `README.md` e o script `rt`, que o módulo `project` usa ([docs/modules/project.md](project.md)).
9. Imprime o help.

## Edições no `platform.yaml`

O arquivo da plataforma de partida é editado linha a linha, e os comentários dela ficam. Um cabeçalho acima de tudo marca o arquivo como criado pelo comando, e por isso uma plataforma criada nunca é escolhida como partida de outra.

| Escolha | Linhas alteradas |
| :--- | :--- |
| Nome | `platform` e `top` |
| `--profile` | bloco `core` (`type`, `base`, `extensions`) |
| `--rom` | Tamanho da região de FLASH e as duas bancas de `flash`, divididas em setores inteiros |
| `--ram` | Tamanho da região de RAM e as palavras `stdout`, `tohost` e `fromhost` no topo dela |
| `--icache`, `--dcache` | Linha da cache em `memory`, com `enabled: false` quando `off` |

Os periféricos, os relógios, as entradas e saídas e as interrupções vêm da plataforma de partida. Uma plataforma de partida sem alguma das linhas esperadas é recusada com a linha que falta.

## Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_new_project.py::test_sizes_are_read_in_bytes` | `64K`, `1M` e números viram bytes |
| `tests/test_new_project.py::test_a_malformed_size_is_refused` | Tamanhos malformados são recusados |
| `tests/test_new_project.py::test_caches_are_a_size_or_off` | A cache é um número de bits ou `off` |
| `tests/test_new_project.py::test_the_choices_are_checked_against_the_catalog` | Nome, placa, perfil e tamanhos inválidos são recusados |
| `tests/test_new_project.py::test_a_profile_without_zifencei_is_refused_when_the_boot_needs_it` | Sem Zifencei, o perfil é recusado quando a BOOT_MEMORY executa `fence.i`, com o perfil certo na mensagem |
| `tests/test_new_project.py::test_a_boot_without_fence_i_accepts_any_profile` | Sem `fence.i` na BOOT_MEMORY o perfil é livre |
| `tests/test_new_project.py::test_the_host_words_sit_at_the_top_of_the_ram` | As palavras do hospedeiro seguem o fim da RAM |
| `tests/test_new_project.py::test_the_flash_splits_into_two_banks_of_whole_sectors` | As bancas ocupam setores inteiros |
| `tests/test_new_project.py::test_the_platform_file_follows_the_choices` | O `platform.yaml` reflete todas as escolhas e guarda os comentários |
| `tests/test_new_project.py::test_a_choice_left_out_keeps_the_template_value` | Uma escolha omitida mantém o valor da partida |
| `tests/test_new_project.py::test_a_template_without_the_expected_line_is_refused` | Uma linha esperada que falta é um erro |
| `tests/test_new_project.py::test_names_are_renamed_in_text` | Pasta, nomes VHDL e nomes de projeto são renomeados, sem duplicar |
| `tests/test_new_project.py::test_the_template_is_the_platform_of_the_board` | A partida é a única plataforma da placa |
| `tests/test_new_project.py::test_paths_gain_the_platform_and_its_three_components` | O `paths.yaml` ganha a plataforma e os três componentes |
| `tests/test_new_project.py::test_the_script_gains_a_line_or_reports_none` | O script ganha a linha, ou o comando avisa que não há uma para copiar |
| `tests/test_new_project.py::test_the_platform_is_created_and_registered` | Arquivos, entidade e registros mudam |
| `tests/test_new_project.py::test_nothing_is_copied_when_the_repository_cannot_be_edited` | Nenhuma pasta fica pela metade |
| `tests/test_new_project.py::test_an_existing_platform_is_not_overwritten` | Uma plataforma existente não é sobrescrita |
| `tests/test_new_project.py::test_the_command_prints_the_help_and_runs_without_config` | O comando roda sem `--config` e imprime o help |
| `tests/test_new_project.py::test_the_help_can_be_printed_in_english` | `--lang en` imprime o help em inglês |
| `tests/test_new_project.py::test_the_command_refuses_an_unknown_board` | Uma placa desconhecida termina com status 1 |
| `tests/test_new_project.py::test_a_name_gives_a_slug` | Maiúsculas, acentos, espaços, sublinhados e hifens viram um identificador |
| `tests/test_new_project.py::test_a_name_with_forbidden_characters_is_refused` | Nome vazio, só espaços, barra, ponto, aspas, controle, shell e YAML são recusados |
| `tests/test_new_project.py::test_a_name_whose_slug_does_not_start_with_a_letter` | O identificador passa na mesma validação de antes |
| `tests/test_new_project.py::test_the_name_goes_to_the_header_manifest_help_and_readme` | O nome digitado aparece no cabeçalho, no manifesto, no help e no README |
| `tests/test_new_project.py::test_a_dangerous_name_is_refused_before_anything_is_written` | Um nome perigoso termina com status 1 sem criar nada |
| `tests/test_new_project.py::test_two_names_with_one_slug_collide_and_say_the_slug` | Dois nomes com o mesmo identificador colidem e a mensagem cita o identificador |
| `tests/test_new_project.py::test_an_existing_project_folder_is_refused_with_the_slug` | A pasta do identificador já existente é recusada |
| `tests/test_new_project.py::test_the_positional_name_is_gone` | O argumento posicional não existe mais |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
