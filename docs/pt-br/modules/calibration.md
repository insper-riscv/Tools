# `calibration`

Mede a área dos perfis de uma família com o comando de compilação do projeto e ajusta os coeficientes do estimador de `fit_estimate`. O módulo não sintetiza por conta própria. Num projeto escrito à mão roda o script que ele já tem (`de0-cv_synth.tcl map`); num projeto de placa (`project.board` na lista de perfis) escreve o projeto com `board generate` e roda o `compile.tcl` único do `program`, só até a síntese (`quartus_map`) ou, com `--stop-after fit`, também até o ajuste.

## Medida de um perfil

Para cada perfil da lista o laço executa, nesta ordem:

1. copia o projeto para uma pasta de trabalho (o projeto original nunca muda);
2. escreve o perfil no `platform.yaml` da cópia (perfil, `extras`, tamanhos das caches) e regenera o pacote do mapa de memória com `generate-memory-map`;
3. completa o pacote com as constantes das interrupções que o topo ainda lê quando o perfil não tem interrupções;
4. com `project.board`, escreve o projeto da placa com `riscv-tools --board <placa> board generate --target ...`, de modo que o pacote do mapa de memória da cópia entra no `.qsf` como fonte;
5. calcula o hash das fontes que o Quartus lê (as do `.qsf` e o `platform.yaml`);
6. toma o travamento da máquina (`/tmp/quartus-<máquina>.lock`, o mesmo das outras trilhas) e roda `quartus_sh -t <script> <semente> <map|fit> [GENERIC=valor ...]`, em que o script é o do projeto ou o `compile.tcl` de `program --stop-after`;
7. lê o `*.map.rpt` e o `*.map.summary` (e, com `fit`, o `*.fit.rpt` e o `*.fit.summary`) e grava um registro YAML.

Um perfil cujo registro já traz o mesmo hash, semente e generics é pulado, de modo que uma execução interrompida continua de onde parou.

## Registro bruto

Um arquivo por perfil, em `boards/calibration/raw/<família>/<id>.yaml`.

| Campo | Conteúdo |
| :--- | :--- |
| `id`, `group`, `profile`, `extras`, `icache_kbit`, `dcache_kbit`, `generics`, `holdout` | o perfil medido |
| `seed` | semente passada ao script |
| `tool` | versão do Quartus |
| `sources_hash` | SHA-256 dos caminhos e do conteúdo das fontes |
| `revisions` | commit do projeto e de cada submódulo (o do Core identifica o núcleo calibrado) |
| `added_constants` | constantes completadas no pacote |
| `command` | comando de compilação executado |
| `result` | lógica, registradores, bits de RAM, multiplicadores, PLLs e pinos da síntese |
| `fit_result` | os mesmos campos lidos do ajuste (só com `--stop-after fit`) |
| `entities` | hierarquia até o primeiro nível |

## Ajuste

O modelo é linear nos coeficientes, e o ajuste é de mínimos quadrados sobre os perfis que não são de validação. Colunas que nenhuma combinação das anteriores separa ficam `null` (lista `unseparated`). Os termos que o topo fixo da placa carrega em toda medida entram em `fixed` com valor zero (a SDRAM, a FLASH, o display, a JTAG UART e o controlador de FLASH ficam dentro do termo do núcleo), e o termo de cada cache vale $c_0 = -s_{ref}\,c_1$, porque o tamanho de referência já está no núcleo.

O erro registrado traz o erro médio quadrático sobre os perfis do ajuste (`rms_pct`), o maior erro absoluto sobre os de validação (`max_pct`) e a razão entre o ajuste e a estimativa da síntese (`map_to_fit_ratio`). A razão é a média de `fit_result.logic` sobre `result.logic` dos registros que trazem `fit_result` (`fit_ratio_check`); sem nenhum, vale a faixa conhecida do perfil completo (`known_fit` da lista de perfis, usada na Cyclone V).

## Funções

| Função | Faz |
| :--- | :--- |
| `load_profile_list(arquivo)` | lê a lista de perfis de uma família |
| `run_all(plano, configuração, ids)` | mede os perfis, um de cada vez |
| `measure(plano, perfil, configuração)` | mede um perfil e grava o registro |
| `machine_lock(arquivo)` | travamento exclusivo da máquina (`flock`) |
| `load_records(pasta)`, `fit_table(plano, registros)`, `write_table(conteúdo, arquivo)` | ajusta e grava a tabela de calibração |
| `fit_ratio_check(plano, registros)` | razão ajuste sobre síntese medida nos registros com `fit_result` |

## Comando

```bash
riscv-tools --root <Insper-RISC-V> calibrate run --profiles boards/calibration/profiles/cyclone-v.yaml --raw boards/calibration/raw/cyclone-v [--only id1,id2] [--stop-after map|fit] [--riscv-tools "<comando>"] [--work-dir PASTA] [--lock ARQUIVO] [--keep]
riscv-tools --root <Insper-RISC-V> calibrate fit --profiles boards/calibration/profiles/cyclone-v.yaml --raw boards/calibration/raw/cyclone-v --table boards/calibration/cyclone-v.yaml
```

## Testes

`tests/test_calibration.py` usa um `riscv-tools` e um `quartus_sh` de mentira e cobre os nomes de perfil, a escrita do perfil no `platform.yaml`, a complementação do pacote, o hash das fontes, o registro, a retomada, o erro de síntese, o travamento e o ajuste que recupera coeficientes conhecidos.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
