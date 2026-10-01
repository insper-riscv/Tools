# Configuração

Todo comando do `riscv-tools` recebe `--config <path>`, apontando para o
`config.yaml` **do próprio projeto consumidor**: este pacote nunca traz os
valores de um projeto específico, só padrões (veja `riscv_tools/settings.py`
para a lógica de mesclagem, se tiver curiosidade, mas você não precisa lê-lo
para usar isto).

## Como é montada

Cada módulo tem um pequeno conjunto de padrões no próprio `__config__.py`
(por exemplo `riscv_tools/mailbox/__config__.py`). O `riscv-tools` mescla todos
eles e depois aplica o `config.yaml` do seu projeto por cima: o seu
config.yaml sempre vence. Uma chave sem um padrão razoável entre projetos
(um endereço de memória, um caminho dentro do seu repositório) é `None` nos
padrões embutidos, o que significa que o seu `config.yaml` **precisa**
defini-la: toda chave assim está marcada como "**obrigatória**" abaixo.

Um arquivo de configuração pode partir de outro com `extends: <caminho>`
(relativo ao arquivo que o declara). O arquivo é mesclado por cima da sua
base com as mesmas regras: uma seção presente nos dois é mesclada chave a
chave, e qualquer outro valor (inclusive uma lista) substitui o da base. Uma
variante lista só o que muda, por exemplo um perfil de simulação que altera
o `sim:` e mantém o resto. Uma cadeia que volta a si mesma é um erro.

## Referência

O seu `config.yaml` é um YAML aninhado com estas seções de nível superior.
Qualquer chave omitida volta ao padrão embutido mostrado.

### `toolchain:`

| Chave | Padrão | Usada por |
|---|---|---|
| `gcc` | `riscv32-unknown-elf-gcc` | `compiler`, `c_to_asm`, `boot_rom` |
| `objcopy` | `riscv32-unknown-elf-objcopy` | `compiler`, `boot_rom`, `certify`, `golden_generator` |
| `nm` | `riscv32-unknown-elf-nm` | `golden_generator` (`generate-golden`) |
| `libc` | `none` | `compiler`: a biblioteca C com que os testes linkam. `none` passa `-nostdlib`, então o projeto fornece o que precisar (como `malloc`) por `paths.syscalls`. `picolibc` passa `--specs=picolibc.specs` (e `-Wl,--no-gc-sections`, veja [compiler.md](modules/compiler.md#biblioteca-c)) para um GCC configurado com picolibc, como o que o `GCC_SETUP.md` do Infra compila |
| `specs` | não definida | `compiler`: caminho (relativo à raiz do projeto) de um arquivo de especificação do GCC que descreve a sua plataforma. Ele inclui o `picolibc.specs` e acrescenta o mapa de memória (`--defsym=__flash=...`, `__ram=...`) e o `crt0` a usar, então os testes linkam com o `crt0` e o `picolibc.ld` da própria toolchain e não precisam de `crt0.S` nem de linker script seu. Os testes são então compilados como programas hospedados (o `main` pode retornar), e `libc` é ignorada. Veja [compiler.md](modules/compiler.md#arquivo-de-especificação-da-plataforma) |

### `isa:`

| Chave | Padrão | Usada por |
|---|---|---|
| `base` | `i` | `compiler`, `c_to_asm`: a letra da ISA base, sempre implícita mesmo quando um teste não tem o cabeçalho `RV32_EXT` |
| `canonical_order` | `MAFDQLCBJTPVNH` | `compiler`, `c_to_asm`: a ordem das letras em que as extensões de `RV32_EXT` de um teste são ordenadas (veja [creating-a-c-test.md](creating-a-c-test.md#comentários-de-cabeçalho)) |
| `default_ext` | `""` | **não é lida por nenhum caminho de código atualmente**: declarada aqui só para documentação; um teste sem o cabeçalho `RV32_EXT` sempre resolve para a `base` pura, independentemente do valor definido aqui |

### `paths:` (sem padrão genérico; caminhos dentro do SEU repositório)

Todas são **obrigatórias**, exceto `crt0`, `linker_script` e `sources`.

| Chave | Significado |
|---|---|
| `include_dir` | Passado como `-I` ao gcc: onde fica o seu `rv32_test.h` |
| `crt0` | Caminho do `crt0.S` do seu projeto, compilado e linkado em todo teste. Deixe sem definir com `toolchain.specs`, que seleciona o `crt0` da toolchain |
| `linker_script` | Caminho do linker script do seu projeto. Deixe sem definir com `toolchain.specs`: o driver do GCC então acrescenta o `picolibc.ld` da toolchain |
| `sources` | Lista de arquivos-fonte (relativos à raiz do projeto) compilados em todo teste: as partes do runtime que são da plataforma, como o `_exit` em que o `crt0` da toolchain termina. Vazia por padrão |
| `build_dir` | Onde os artefatos compilados (`.elf`/`.bin`/`.mif`/`.hex`/`manifest.json`) são escritos |
| `c_dir` | Diretório com uma pasta `<name>/src.c` por teste em C (veja [creating-a-c-test.md](creating-a-c-test.md)) |
| `asm_dir` | Diretório com uma pasta `<name>/src.S` por teste em assembly (veja [creating-an-asm-test.md](creating-an-asm-test.md)) |

Não há divisão `tests_real_dir`/`tests_sim_dir`/`golden_dir`: todo teste em `c_dir`/`asm_dir` é compilado tanto para `compile --emit mif` (real) quanto para `--emit hex` (sim), qualquer que seja o tipo: os `results` de um teste `RV32_TEST_KIND: memory` são comparados com o golden.json da mesma forma nos dois (veja [creating-a-c-test.md](creating-a-c-test.md#testes-unit-versus-memory): `memory` é `unit`, expandido: PASS no mailbox primeiro, depois a comparação com o golden). O mapa `{endereço de byte: valor de byte}` esperado de um teste `memory` fica em `<name>/golden.json`, ao lado do `src.c`/`src.S`, e não num diretório de goldens separado.

### `quartus:`

| Chave | Padrão | Usada por |
|---|---|---|
| `jtag_device` | **obrigatória** | `jtag`: a string de IDCODE JTAG da própria FPGA. O nome do cabo (`USB-Blaster [...]`) é detectado em tempo real, já que muda entre reboots |
| `project_dir` | **obrigatória** | `quartus_program`: caminho do diretório do projeto Quartus |
| `project_name` | **obrigatória** | `quartus_program`: passado a `quartus_sh --flow compile` |
| `sof_file` | **obrigatória** | `quartus_program`: caminho (relativo a `project_dir`) do `.sof` compilado, passado ao `quartus_pgm` |
| `rom_mif_target` | **obrigatória** | `quartus_program`: caminho (relativo a `project_dir`) de onde a megafunção da ROM lê o `init_file` na compilação |
| `stale_cache_dirs` | `[db, incremental_db, output_files, simulation]` | `quartus_program`: diretórios (relativos a `project_dir`) apagados antes de toda compilação, já que o `init_file` de uma ROM não é um fonte rastreado do projeto |
| `rom_mem_instances` | `[0]` | `rom_writer`: índice(s) da instância do In-System Memory Content Editor da ROM (uma lista; um projeto com mais de uma cópia física da ROM, por exemplo uma por porta de leitura quando uma memória dual-port verdadeira não está disponível, lista todas, mantidas em sincronia a cada escrita) |
| `ram_mem_instance` | `1` | `ram_zero`, `ram_dump`, `mailbox`: o mesmo, para a RAM |
| `poll_interval_seconds` | `0.5` | `mailbox` / `orchestrator`: de quanto em quanto tempo consultar o mailbox enquanto espera um teste |
| `program_wait_seconds` | `15` | `orchestrator`: quanto esperar após uma reconfiguração completa (só no caminho de fallback) antes de ler o mailbox |
| `default_timeout_s` | `15` | `compiler` / `orchestrator`: timeout padrão por teste se o teste não tem o cabeçalho `RV32_TIMEOUT_S` |

### `memory:` (todas **obrigatórias**, sem padrão genérico; dependem da profundidade da sua RAM/ROM)

| Chave | Significado |
|---|---|
| `ram_base` | Endereço de byte base da RAM |
| `mailbox_addr` | Endereço de byte da palavra do mailbox PASS/FAIL |
| `go_flag_addr` | Endereço de byte da palavra da flag "go" de reinício |
| `ram_words` | Profundidade da RAM em palavras: usada para zerar a RAM inteira e validar o `.mif` de um programa |
| `rom_base` | Endereço de byte em que a imagem do programa é linkada (0 para uma ROM que começa no endereço 0). O `.mif`/`.hex` de um teste linkado acima de 0 recebe `rom_base / 4` palavras zero à esquerda, porque a memória é endereçada de forma crua, sem subtrair uma base |
| `rom_words` | Profundidade da ROM em palavras: usada para validar/formatar o `.mif` de um programa |

### `emulator:`

| Chave | Padrão | Usada por |
|---|---|---|
| `spike_bin` | `spike` | `golden_generator`: nome/caminho do binário `spike`. Ele precisa manter o módulo de debug longe do endereço 0 (veja [generating-a-golden.md](generating-a-golden.md#requisitos)) |
| `timeout_s` | `60` | `golden_generator`: segundos de espera até um teste escrever `tohost`, antes de a geração falhar |
| `tohost_symbol` | `tohost` | `golden_generator`: o símbolo HTIF que o Spike observa até uma escrita diferente de zero. Convenção padrão; raramente precisa ser alterado |
| `sources` | `[]` | `golden_generator`, `spike_run`: arquivos-fonte (relativos à raiz do projeto) linkados no ELF que o Spike executa e não na imagem do próprio teste. Para uma imagem que termina em código que, no hardware, fica em outro lugar (uma rotina da boot ROM num endereço fixo): um substituto dela, mais os símbolos `tohost` e `fromhost` de que o Spike precisa. Vazia, o Spike executa a imagem do próprio teste |
| `gcc_flags` | `[]` | `golden_generator`, `spike_run`: argumentos extras do gcc para esse ELF, por exemplo um `-D` que faz o arquivo de especificação omitir o endereço fixo do hardware |

### `sim:` (exige o extra `sim`, `uv sync --extra sim`)

| Chave | Padrão | Usada por |
|---|---|---|
| `toplevel` | **obrigatória** | `sim_runner`: nome da entidade VHDL de topo que o GHDL elabora e à qual o cocotb se conecta |
| `vhdl_sources` | **obrigatória** | `sim_runner`: lista de caminhos de fontes VHDL (relativos à raiz do seu projeto), em ordem de dependência |
| `test_module` | **obrigatória** | `sim_runner`: o módulo de teste cocotb do seu projeto (por exemplo `sim.test_c_program`), que conhece a hierarquia real de sinais do DUT e consulta o mailbox PASS/FAIL, a mesma convenção que o `mailbox` usa no hardware real, só que lendo direto os sinais simulados em vez de JTAG |
| `ghdl_std` | `08` | `sim_runner`: valor do `--std=` do GHDL. VHDL-2008 (IEEE Std 1076-2008) por padrão, acompanhando o teto do próprio Quartus: o Quartus (mesmo o mais recente, 25.1std) só aceita `VHDL93`/`VHDL_2008` em `VHDL_INPUT_VERSION`, e `VHDL_2019` é rejeitado de cara, então isso mantém simulação e síntese no mesmo dialeto |
| `parameters` | `{}` | `sim_runner`: generics VHDL a definir no `toplevel` na etapa de execução do GHDL, por exemplo `{"ROM_FILE": "{hex_path}"}` para um projeto cujo modelo de ROM só de simulação carrega a imagem do programa por um generic VHDL, em vez de ler a variável de ambiente `ROM_HEX` do próprio `sim_runner`. `"{hex_path}"` é substituído pelo caminho do `.hex` compilado de cada teste; qualquer outro valor é repassado como está (por exemplo um generic de profundidade de memória fixa). Vazio por padrão: a maioria dos toplevels não precisa sobrescrever generics |
| `hex_format` | `words` | `compile --emit hex`, `sim`, `certify`: layout do `.hex` que uma simulação carrega. `words` é uma palavra de 32 bits por linha, com palavras zero à esquerda para um programa linkado acima do endereço 0. `verilog` é o que o `objcopy -O verilog` escreve (veja [compiler.md](modules/compiler.md#formato-do-arquivo-hex)), então o modelo de memória que o carrega precisa tratar linhas `@<endereço de palavra>` e quatro palavras por linha |
| `image` | `hex` | `sim`: qual imagem a simulação carrega. `hex` lê `<build_dir>/sim/manifest.json` (de `compile --emit hex`). `mif` lê `<build_dir>/real/manifest.json` (de `compile --emit mif`), as mesmas imagens que o hardware carrega, e também gera o `.mif` da boot ROM |
| `ghdl_flags` | `[]` | `sim_runner`: argumentos extras do GHDL nas etapas de análise, elaboração e execução, por exemplo `["-fsynopsys", "-fexplicit"]` para uma biblioteca de simulação de fornecedor |
| `libraries` | `{}` | `sim_runner`: bibliotecas VHDL analisadas uma vez por execução do `sim`, antes de `vhdl_sources`, como `{biblioteca: [arquivos]}`, por exemplo a `altera_mf` do Quartus para um toplevel que instancia a IP de memória dele. Os caminhos são relativos à raiz do projeto, e `$VAR` ou `${VAR}` é substituído a partir do ambiente (variável não definida é um erro) |
| `run_files` | `{}` | `sim_runner`: arquivos copiados para o diretório de execução de cada teste antes de ele rodar, como `{nome do arquivo: origem}`, para um projeto que abre um arquivo por um nome fixo, por exemplo o `init_file` de um `altsyncram`. A origem aceita os mesmos modelos que `parameters` |
| `env` | `{}` | `sim_runner`: variáveis de ambiente extras para o módulo de teste cocotb, como `{nome: modelo}`, com os mesmos modelos que `parameters` |
| `python_path` | `[]` | `sim_runner`: diretórios (relativos à raiz do seu projeto) colocados no caminho de módulos da simulação, para que o `test_module` possa ficar fora do seu projeto, por exemplo no repositório da plataforma que um `extends:` da configuração usa |

Os modelos de `parameters`, `run_files` e `env` são `{hex_path}` e `{mif_path}` (a imagem do teste, a que o `image` seleciona; a outra fica vazia), e `{boot_rom_hex_path}` e `{boot_rom_mif_path}` (as da boot ROM, iguais para todos os testes).

### `freq_sweep:` (só necessária para `riscv-tools freq-sweep`)

Descreve o *formato* das strings de parâmetro do fonte do seu PLL: nenhuma
delas tem um padrão razoável entre projetos, já que os nomes de instância e as
convenções de parâmetros das megafunções de PLL são específicos de cada
projeto. Veja [finding-fmax.md](finding-fmax.md) para saber para que serve e
como rodar um sweep.

| Chave | Padrão | Usada por |
|---|---|---|
| `pll_file` | **obrigatória** | `freq_sweep`/`orchestrator`: caminho (relativo à raiz do seu projeto) do fonte Verilog/VHDL do PLL, reescrito antes da compilação de cada frequência candidata |
| `phase_count` | `1` | `freq_sweep`: quantas saídas de clock com fases igualmente espaçadas a instância do PLL tem (por exemplo `3` para um PLL de três vias 0/120/240 graus). `1` (um PLL simples de fase única) cobre a maioria dos projetos |
| `freq_param_template` | `output_clock_frequency{idx}` | `freq_sweep`: nome de parâmetro com `{idx}` (indexado a partir de 0), procurado e reescrito. Corresponde à megafunção `altpll` do Quartus; sobrescreva para outra megafunção ou nomenclatura de instância |
| `phase_param_template` | `phase_shift{idx}` | `freq_sweep`: a mesma ideia, para o parâmetro de defasagem |
| `freq_unit` | `MHz` | `freq_sweep`: sufixo literal de unidade escrito depois do valor de frequência, por exemplo `.output_clock_frequency0("10.000000 MHz")`. Só controla o sufixo da string: a conta de período/defasagem em si sempre assume MHz na entrada e ps na saída, seguindo a convenção do `altpll` do Quartus |
| `phase_unit` | `ps` | `freq_sweep`: a mesma ideia, para o valor da defasagem |

O `riscv-tools freq-sweep <mif> --golden <golden.json>` reaproveita
`quartus.*`/`memory.ram_base` das seções `quartus:`/`memory:` acima (os mesmos
campos que `full_reconfigure`/`run_one` usam) para a compilação, programação,
dump e comparação de cada frequência candidata. Veja
`orchestrator.run_freq_sweep_linear`/`run_freq_sweep_binary`.

### `run_log:`

Onde `run`/`sim`/`certify` mantêm, cada um, o próprio histórico de logs
persistente e ignorado pelo git. Veja `run_log.start`.

| Chave | Padrão | Usada por |
|---|---|---|
| `logs_dir` | `logs` | `cli` (cmd_run/cmd_sim/cmd_certify): caminho (relativo à raiz do seu projeto) com um subdiretório por subcomando (`real`/`sim`/`certification`), cada um com um `latest.log` da execução em andamento mais toda execução anterior arquivada sob o próprio timestamp de início. Adicione `logs/` ao `.gitignore` do seu projeto |

## Exemplo

Um `config.yaml` mínimo que cobre todas as chaves obrigatórias:

```yaml
toolchain:
  gcc: riscv32-unknown-elf-gcc
  objcopy: riscv32-unknown-elf-objcopy

paths:
  include_dir: tools/riscv_build/include
  crt0: tools/riscv_build/crt0.S
  linker_script: tools/riscv_build/link.ld
  build_dir: build
  c_dir: c
  asm_dir: asm

memory:
  ram_base: 0x00000000
  ram_words: 4096
  rom_words: 8192
  mailbox_addr: 0x00003FFC
  go_flag_addr: 0x00003FF8

quartus:
  jtag_device: "@1: 5CE(BA4|FA4) (0x02B050DD)"
  project_dir: ../RV32IM/tests/FPGA/core/quartus
  project_name: core_fpga_test
  sof_file: output_files/core_fpga_test.sof
  rom_mif_target: init.mif
```

Todo o resto (`isa.*`, `quartus.rom_mem_instances`/`ram_mem_instance`/
`poll_interval_seconds`/`program_wait_seconds`/`default_timeout_s`,
`emulator.*`) é opcional: sobrescreva só o que não combina com o seu setup.

A `sim:` nem aparece neste exemplo mínimo: os caminhos de hardware real e de
geração de goldens nunca a tocam, então ela só é necessária quando você passa a
usar o `sim_runner`/`riscv-tools sim`, e nesse momento
`toplevel`/`vhdl_sources`/`test_module` passam a ser obrigatórias (veja a
Referência de configuração acima).

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../LICENSE).
