# `memory_map`

Confere que todas as cópias escritas à mão do mapa de memória de uma plataforma concordam. O mapa (bases e tamanhos das regiões, as palavras que a memória de boot reserva no topo da RAM, os pontos de entrada do boot, as janelas dos periféricos) é necessário em muitos arquivos: flags do linker, memória de boot, runtime C, VHDL, IPs do Quartus, o `config.yaml` do projeto. Cada cópia só é notada quando diverge na placa. Um arquivo YAML, a plataforma, é a fonte da verdade; este módulo lê cada cópia e reporta toda divergência.

## 1. Configuração

Sem seção no `config.yaml`: o arquivo da plataforma se descreve sozinho e é passado com `--platform`.

```yaml
regions:                      # o mapa em si
  - {name: BOOT_MEMORY, base: 0x0,    size: 2K,   kind: rom, exec: true}
  - {name: FLASH,    base: 0x800,  size: 30K,  kind: rom, exec: true}
  - {name: RAM,      base: 0x8000, size: 160K, kind: ram}
reserved:                     # palavras no topo da RAM (dentro de uma região ram)
  stdout:  {base: 0x2FBE0, size: 1K+8}
  tohost:  {base: 0x2FFF0, size: 16}
boot: {entry: 0x800, wait_restart: 0x100}
peripherals:                  # base = janela | id << (address_bits - 4)
  - {name: GPIO, base: 0xA0000000, id: 2}
checks:                       # onde mora cada cópia
  - name: config ram base
    file: tools/riscv_build/config.yaml      # relativo a --root
    yaml: memory.ram_base                     # caminho com pontos, ou:
    expect: RAM.base
  - name: specs ram size
    file: rv32im-fpga.specs
    pattern: '--defsym=__ram_size=(\S+)'      # um grupo de captura
    expect: RAM.size - (RAM.end - stdout.base)
```

- **Símbolos** em `expect`: `<REGIÃO>.base|size|end|words`, `<reservado>.base|size|end`, `boot.entry|wait_restart`, `<PERIFÉRICO>.base|id`.
- **Números** aceitam hexadecimal, decimal, VHDL (`16#800#`), sufixos (`30K`, `0x800u`) e `+ - * /` (divisão exata), além de `log2()` (exato) e `clog2()` (arredonda para cima, para larguras de endereço).
- Um check cujo padrão não casa nada **falha** ("a cópia mudou de lugar"); `optional: true` ignora um arquivo ausente. Um padrão com vários casamentos precisa concordar em todos.
- Antes de ler as cópias, o próprio mapa é validado: regiões e palavras reservadas não se sobrepõem, as reservadas ficam dentro de uma região RAM, `boot.entry` está numa região executável, `boot.wait_restart` está na primeira região, a base de cada periférico bate com o id, e toda região termina na janela de periféricos ou antes (a metade inferior do espaço é da BOOT_MEMORY, da ROM e da RAM, e a superior, dos periféricos; `0x80000000` com 32 bits, ver a seção 9).

## 2. Gerar os arquivos do mapa

O mesmo YAML pode dizer, na seção `generate`, quais arquivos saem dele, de modo que nenhuma cópia do mapa precise ser escrita à mão.

| Chave | Arquivo gerado | Conteúdo |
| :--- | :--- | :--- |
| `specs` | Arquivo de specs do GCC | As flags do linker: `__flash`, `__flash_size`, `__ram`, `__ram_size` e `rv32_wait_restart`. A RAM do linker termina onde começa a palavra reservada `ram_limit` |
| `boot_ld` | Linker script da memória de boot | A memória `boot_memory` na primeira região e o `RESET_RESERVED` de `boot.wait_restart` |
| `runtime` | Cabeçalho do runtime (`.h`, também incluído por `.S`) | `RV32_RAM_END` (fim da RAM `ram`), `RV32_TOHOST_ADDR`, `RV32_FROMHOST_ADDR` e `RV32_STDOUT_BASE`, das faixas `reserved` que o mapa tem, `RV32_BOOT_ENTRY` (para onde a memória de boot salta) e `RV32_<NOME>_BASE` de cada periférico; o runtime em C e em assembly (`_exit.c`, `stdio.c`, `boot_memory.S`, `spike_exit.S`) usa esses nomes no lugar de endereços escritos à mão |
| `config_pkg` | Pacote VHDL de constantes da plataforma | O `config_pkg` da seção 10, ao lado do pacote do mapa |
| `vhdl` | Pacote VHDL | As constantes `BOOT_MEMORY_BITS`, `BOOT_MEMORY_SIZE_BYTES`, `ROM_BASE_KIB`, `ROM_END_KIB`, `ROM_STORAGE_BYTES`, `RAM_BASE_KIB`, `RAM_END_KIB`, `RAM_STORAGE_BYTES`, `RAM_LAST_PAGE`, `EXT_BASE_KIB` e `PERIPH_BASE_KIB`, as flags `ROM_EXTERNAL` e `RAM_EXTERNAL` (de `generate.vhdl` ou da seção `memory`), as constantes das caches da seção `memory` e, de cada periférico, `<NOME>_BASE` e `<NOME>_ID` |

```yaml
generate:
  specs: {path: runtime/rv32im-fpga.specs, rom: FLASH, ram: RAM, ram_limit: stdout}
  boot_ld: {path: runtime/boot_memory.ld}
  runtime: {path: runtime/memory_map.h, ram: RAM}
  vhdl:
    path: rtl/map_pkg.vhd
    package: map_pkg
    rom: FLASH
    ram: RAM
```

`ext_base` e `periph_base` são opcionais e valem `0x80000000`, a janela dos periféricos. `ROM_STORAGE_BYTES` e `RAM_STORAGE_BYTES` são a menor potência de dois que cobre o fim da ROM e o tamanho da RAM, e `RAM_LAST_PAGE` são os bits 31:12 da última página de 4 KiB da RAM.

Os limites do pacote VHDL são os genéricos do `core`, em KiB, então um endereço que não é múltiplo de 1 KiB é um erro. O mapa é validado antes de gerar, e um mapa inconsistente não gera nada.

```bash
uv run riscv-tools --root <projeto> generate-memory-map --platform src/platform/platform.yaml
uv run riscv-tools --root <projeto> generate-memory-map --platform src/platform/platform.yaml --check
```

Com `--check` nada é escrito, e o comando sai com status 1 se um arquivo faltar ou estiver diferente do que o mapa geraria. Não precisa de `--config`.

## 3. As bancas da FLASH

A seção `flash` do `platform.yaml` divide a FLASH em bancas, cada uma com uma imagem no formato do [`flash_image`](flash_image.md), para a atualização de programa em campo.

```yaml
flash:
  region: FLASH
  banks:
    - {name: A, base: 0x1000,  size: 124K}
    - {name: B, base: 0x20000, size: 128K}
generate:
  bank_specs:
    - {path: runtime/bank-b.specs, rom: BANK_B_PAYLOAD, ram: RAM, ram_limit: stdout}
  banks_h: {path: runtime/flash_banks.h}
```

Cada banca começa por uma página de cabeçalho de 256 bytes, então o programa dela é ligado a partir de `base + 256`. O mapa ganha, para a banca `A`, os símbolos `BANK_A.base|size|end|words` e `BANK_A_PAYLOAD.base|size|end|words` (a parte depois do cabeçalho), que servem de `expect` nos checks e de `rom` nas seções de specs.

| Chave | Arquivo gerado | Conteúdo |
| :--- | :--- | :--- |
| `bank_specs` | Lista de arquivos de specs do GCC, um por entrada | Como `specs`, com `__flash` e `__flash_size` da região escolhida em `rom`, que costuma ser `BANK_<nome>_PAYLOAD` |
| `banks_h` | Cabeçalho (`.h`, também incluído por `.S`) | `RV32_IMAGE_MAGIC`, `RV32_IMAGE_HEADER_SIZE` e, de cada banca, `RV32_BANK_<NOME>_BASE`, `_SIZE` e `_ENTRY` (onde o programa começa) |

O mapa recusa bancas que não estejam alinhadas ao setor de 4 KiB, que não deixem espaço para um programa depois do cabeçalho, que saiam da região em `flash.region`, que se sobreponham ou que repitam o nome.

## 4. O perfil da plataforma

A plataforma escolhe o seu perfil em `profile:` (`rv32im`, `rv32em_zicsr`, ...) e diz onde está a especificação dos perfis em `profiles:`, um caminho relativo ao `platform.yaml` (o `profiles/matrix.yaml` do Core). O nome começa por `rv32i` (32 registradores), `rv32e` (16), `rv64i` ou `rv64e` e precisa ser um dos perfis da especificação. Dele saem:

| Saída | Conteúdo |
| :--- | :--- |
| Pacote VHDL | `HAS_E` (verdadeiro no RV32E) e um `HAS_<EXTENSÃO>` booleano por extensão do núcleo (`HAS_M`, `HAS_ZMMUL`, `HAS_ZICSR`, `HAS_ZICNTR`, `HAS_ZIHPM`, `HAS_ZIMOP`, `HAS_ZICOND`, `HAS_ZIHINTNTL`, `HAS_ZIHINTPAUSE`, `HAS_ZIFENCEI`, `HAS_ZICCLSM`, `HAS_INTERRUPTS`, `HAS_SSCOFPMF`, `HAS_ACCESS_FAULTS`) e `PERIPH_SLOTS`, a máscara de 8 bits das janelas de 256 MiB do barramento de periféricos que têm periférico (o bit `n` vale para o `id` `n` da lista `peripherals`) |
| `config.yaml` | `isa.base`, que escolhe o `-march` e o `-mabi` dos programas e da memória de boot (`rv32e` com `ilp32e`, os demais com `ilp32`), e os `sim.parameters` `HAS_E` e `HAS_*` que o runner passa ao GHDL |

`--profile NOME`, opção global do `riscv-tools`, troca o `profile:` da plataforma sem editá-la, para rodar a mesma plataforma sobre vários perfis numa matriz de testes. Vale para o `generate-memory-map` (escreve o pacote daquele perfil), para o `platform sync` e para todo comando que lê a configuração. Um nome que a especificação não lista é rejeitado antes de qualquer coisa rodar.

`extras:` liga o que o perfil não liga, por nome de extensão (`extras: [Zihintntl, Zihintpause, Interrupts, Sscofpmf, AccessFaults]`; a `Sscofpmf` exige o Zihpm no perfil e `Interrupts` nos extras, e a geração falha sem eles), e vale também com `--profile`. A matriz do Core lista Zimop e Zicond como extensões de perfil, então só os nomes que a matriz não lista dependem de `extras:`; os dois primeiros continuam aceitos ali. Toda chave que nem o perfil nem os extras ligam sai `false` no pacote.

```bash
uv run riscv-tools --root <projeto> --profile rv32em_zicsr generate-memory-map --platform src/platform/platform.yaml
```

## 5. As interrupções da plataforma

Uma plataforma com as interrupções de máquina liga o extra `Interrupts` (o núcleo só as habilita se tiver `Zicsr`), lista o `CLINT` e, para as linhas externas, o `EXT_IRQ` entre os `peripherals`, e descreve o relógio na seção `interrupts`.

```yaml
extras: [Interrupts]
peripherals:
  - {name: CLINT,   base: 0xE0000000, id: 6}
  - {name: EXT_IRQ, base: 0xF0000000, id: 7}
interrupts:
  clock_hz: 50000000   # relógio do domínio do núcleo e do CLINT
  mtime_hz: 1000000    # taxa com que o mtime do CLINT conta
```

O `mtime` do CLINT é um contador próprio, ajustado por `mtime_hz`, e é independente do CSR `time` da Zicntr, que o núcleo atende. Com `clocks.core` na plataforma o `clock_hz` é omitido e vale o relógio do núcleo arredondado para um número inteiro de ciclos por incremento; escrito, ele precisa ser esse valor. O `clock_hz` precisa ser múltiplo de `mtime_hz`, o perfil precisa ligar `has_interrupts`, e a lista `peripherals` precisa ter o `CLINT`; a ausência de qualquer um deles é um erro antes de gerar e no `check-memory-map`.

| Saída | Constantes |
| :--- | :--- |
| Pacote VHDL (`vhdl`) | `HAS_INTERRUPTS`, `CLOCK_HZ`, `MTIME_HZ` e `CLINT_TICK_CYCLES` (ciclos de relógio por incremento do `mtime`, o genérico `tick_cycles` do CLINT), além de `CLINT_BASE`, `CLINT_ID`, `EXT_IRQ_BASE` e `EXT_IRQ_ID` |
| Cabeçalho do runtime (`runtime`) | `RV32_CLINT_BASE`, `RV32_MSIP`, `RV32_MTIMECMP`, `RV32_MTIME` e `RV32_MTIME_HZ`, que o `FreeRTOSConfig.h` usa em `configMTIMECMP_BASE_ADDRESS`, `configMTIME_BASE_ADDRESS` e `configCPU_CLOCK_HZ` |

Os deslocamentos dos registradores dentro da janela de 64 KiB do CLINT seguem o leiaute da SiFive que o porte do FreeRTOS espera.

### 5.1. PLIC e fontes de interrupção

Uma plataforma com PLIC o lista em `peripherals` com um `size` (a janela que ele decodifica, potência de dois de pelo menos `0x200008` bytes) e o descreve em `interrupts`.

```yaml
peripherals:
  - {name: PLIC, base: 0xF0000000, id: 7, size: 4M}
interrupts:
  plic: {priority_bits: 3}
  sources:                 # identificadores das linhas ligadas ao PLIC
    - {name: UART, id: 1}
    - {name: TIMER, id: 5}
```

| Saída | Constantes |
| :--- | :--- |
| Pacote VHDL (`vhdl`) | `PLIC_N_SOURCES` (o maior identificador), `PLIC_PRIORITY_BITS`, `PLIC_ADDR_WIDTH` (a janela em palavras, como potência de dois) e `IRQ_<NOME>` por fonte |
| Cabeçalho do runtime (`runtime`) | `RV32_PLIC_PRIORITY`, `RV32_PLIC_PENDING`, `RV32_PLIC_ENABLE`, `RV32_PLIC_THRESHOLD`, `RV32_PLIC_CLAIM` e `RV32_IRQ_<NOME>` por fonte |

Identificadores repetidos, fora de 1 a 1023, `priority_bits` fora de 1 a 32 e janela sem `size` ou de tamanho inválido são erros antes de gerar.

$$ \text{msip} = base, \quad \text{mtimecmp} = base + \texttt{0x4000}, \quad \text{mtime} = base + \texttt{0xBFF8} $$

## 6. Os relógios da plataforma

A seção `clocks` do `platform.yaml` é a fonte única das frequências: o PLL, o `.sdc` e o pacote VHDL saem dela (ver [pll_generator](pll_generator.md)). O mapa de memória lê dela o relógio do controlador da SDRAM e o do núcleo.

```yaml
clocks:
  core:  {mhz: 76.923077, phase_ps: 7500}  # relógio do núcleo
  mem:   {mhz: 100}                        # relógio do controlador da SDRAM
```

| Saída | Conteúdo |
| :--- | :--- |
| Pacote VHDL (`vhdl`) | `SDRAM_CLOCK_HZ` e `SDRAM_TCK_PS` de `clocks.mem`, o período em picossegundos com que o controlador e o modelo do chip convertem os tempos do chip em ciclos |
| Símbolos dos `checks` | `CLOCKS.mem_mhz`, `CLOCKS.mem_tck_ps`, `CLOCKS.core_mhz` (arredondado) e `CLOCKS.core_phase_ps` |

Todo relógio declarado precisa de `mhz` positivo, e `clocks.mem` precisa ter período inteiro em picossegundos; a falta ou o excesso é um erro antes de gerar e no `check-memory-map`. A fase do pino `DRAM_CLK` pertence à placa (`memories.sdram.clk_phase_ps` do `board.yaml`). A seção `interrupts` nomeia `INTERRUPTS.tick_cycles`, os ciclos de clock por incremento do `mtime`, para os `checks`.

## 7. As memórias e as caches da plataforma

A seção `memory` do `platform.yaml` escolhe, por plataforma, quatro coisas independentes, e delas saem as 16 combinações. Nenhum campo tem valor padrão, então esquecer um deles é um erro e a plataforma nunca monta uma combinação diferente da que o autor escreveu. Uma plataforma sem a seção continua gerando o pacote de antes.

```yaml
memory:
  rom:    {external: true}
  ram:    {external: true}
  icache: {enabled: true, size_bits: 4096}
  dcache: {enabled: true, size_bits: 4096}
```

| Campo | Tipo | Significado |
| :--- | :--- | :--- |
| `rom.external` | booleano | A FLASH fica fora do chip |
| `ram.external` | booleano | A RAM fica fora do chip |
| `icache.enabled` | booleano | Existe cache de instruções |
| `icache.size_bits` | potência de dois, no mínimo 256 | Tamanho da cache de instruções em bits; obrigatório só com `enabled: true` |
| `dcache.enabled` | booleano | Existe cache de dados |
| `dcache.size_bits` | potência de dois, no mínimo 256 | Tamanho da cache de dados em bits; obrigatório só com `enabled: true` |

Os campos `rom_external` e `ram_external` de `generate.vhdl` saem da seção `memory`, e os dois juntos com ela são um erro.

### 7.1. Constantes geradas

O pacote VHDL ganha as constantes abaixo. `ROM_VIA_PORT` e `RAM_VIA_PORT` são os valores dos genéricos `rom_external` e `ram_external` do núcleo, porque uma cache só existe do lado do protocolo da porta do núcleo.

| Constante | Tipo | Valor |
| :--- | :--- | :--- |
| `ROM_EXTERNAL` | boolean | `memory.rom.external` |
| `RAM_EXTERNAL` | boolean | `memory.ram.external` |
| `HAS_ICACHE` | boolean | `memory.icache.enabled` |
| `HAS_DCACHE` | boolean | `memory.dcache.enabled` |
| `ICACHE_SIZE_BITS` | positive | `memory.icache.size_bits`, ou 256 sem a cache |
| `DCACHE_SIZE_BITS` | positive | `memory.dcache.size_bits`, ou 256 sem a cache |
| `CACHE_WINDOW_BITS` | natural | Menor largura de 26 a 29 tal que a ROM e a RAM cabem cada uma numa janela alinhada de $2^{\text{largura}}$ bytes (26 é 64 MiB, 27 é 128 MiB), derivada das regiões |
| `ROM_VIA_PORT` | boolean | `ROM_EXTERNAL or HAS_ICACHE` |
| `RAM_VIA_PORT` | boolean | `RAM_EXTERNAL or HAS_DCACHE` |

No `config.yaml` os mesmos valores chegam como `sim.parameters` com os mesmos nomes (`ROM_EXTERNAL`, `RAM_EXTERNAL`, `HAS_ICACHE`, `HAS_DCACHE`, `ICACHE_SIZE_BITS` e `DCACHE_SIZE_BITS`; `CACHE_WINDOW_BITS` só quando passa de 26), e o topo de simulação precisa declarar os genéricos correspondentes. Sem `config.addr_widths` na plataforma, as larguras de endereço vêm da escolha, e saem a `boot_memory` e cada memória interna, já que uma memória externa é um chip dimensionado pelo próprio topo. Com `config.addr_widths` listado, a lista vale.

### 7.2. Validação

| Regra | Condição | Resultado |
| :--- | :--- | :--- |
| V1 | Os quatro booleanos existem e não há chave desconhecida | Erro |
| V2 | `size_bits` é potência de dois e vale pelo menos 256 | Erro |
| V3 | Com alguma cache, a ROM e a RAM cabem cada uma numa janela alinhada de até 512 MiB (a tag das caches guarda os bits abaixo da janela) | Erro |
| V4 | Com a ROM pela porta do núcleo, o tamanho dela cabe na janela de 1024 KiB do roteador | Erro |
| V5 | Região `exec` na RAM exige RAM externa e ROM pela porta (ROM externa ou cache de instruções) | Erro |
| V7 | Região `exec` na RAM atrás da cache de instruções exige Zifencei no perfil | Erro |
| V8 | Cache de instruções sobre ROM interna ou cache de dados sobre RAM interna | Aviso |
| V9 | Plataforma com periféricos | Nota |
| V10 | Com alguma cache, `reserved.fromhost` existe e está na última página de 4 KiB da RAM, a que a cache ignora | Erro |

ROM externa sem cache de instruções é válida. O aviso e a nota saem em `NOTE` no erro padrão do `generate-memory-map`, e os erros impedem a geração.

### 7.3. A opção `--memory`

`--memory`, opção global do `riscv-tools`, troca campos da seção `memory` sem editar a plataforma, para rodar a mesma plataforma sobre as 16 combinações. O valor é uma lista de pares `chave=valor` separados por vírgula.

| Chave | Valores |
| :--- | :--- |
| `rom`, `ram` | `int` ou `ext` |
| `icache`, `dcache` | `on`, `off` ou um tamanho em bits, que liga a cache |

Uma chave que não aparece mantém a escolha da plataforma, e uma plataforma sem a seção `memory` exige as quatro chaves. O `on` sem tamanho usa o `size_bits` da plataforma, ou 4096 se ela não tem. Um valor mal formado é rejeitado antes de qualquer coisa rodar.

```bash
uv run riscv-tools --root <projeto> --memory rom=ext,ram=int,icache=on,dcache=off generate-memory-map --platform src/platform/platform.yaml
```

## 8. Ler a configuração do mapa

Um `config.yaml` do projeto declara `memory_map: <caminho do platform.yaml>`, e o carregador de configuração troca as chaves que o mapa fixa pelas dele: `isa.base`, `memory.boot_memory_base`, `boot_memory_words`, `rom_base`, `rom_words`, `ram_base`, `ram_words`, `tohost_addr`, `fromhost_addr` `sim.env.TOHOST_ADDR`, `sim.env.STDOUT_ADDR` (o testbench lê o endereço do ambiente) e, para as memórias que a seção `config.addr_widths` do mapa lista, `sim.parameters.<memória>_addr_width`. O que o mapa fixa vale mais que o que o arquivo ou os seus `extends` dizem, então nenhum endereço nem tamanho é escrito duas vezes.

```yaml
config:
  rom: FLASH
  ram: RAM
  addr_widths: [boot_memory, rom, ram]
```

O `platform sync` grava os valores já trocados, de modo que Tests e Certification não precisam do `platform.yaml`.

## 9. A largura do endereço físico

### 9.1. O campo `address_bits`

O campo de topo `address_bits` do `platform.yaml` é um inteiro de 16 a 64 com a largura do endereço físico. Ausente, vale 32, e nenhuma plataforma escrita para 32 bits precisa mudar. O perfil `rv64...` liga o `IS_64` do `config_pkg`, e acima de 32 bits só um perfil `rv64` é válido.

```yaml
address_bits: 24      # opcional, 32 por padrão
profile: rv32im
peripherals:          # base = 2**(address_bits - 1) | id << (address_bits - 4)
  - {name: UART, base: 0xC00000, id: 4}
```

### 9.2. A janela de periféricos

A janela de periféricos é a metade superior do espaço de endereços, e o identificador do periférico ocupa os três bits abaixo do bit da janela.

$$ \text{janela} = 2^{\text{address\_bits} - 1}, \quad \text{base} = \text{janela} \mid (\text{id} \ll (\text{address\_bits} - 4)) $$

Com 32 bits os valores são `0x80000000` e `id << 28`, os mesmos de antes. O campo de topo `periph_window` fixa outra base para a janela, e o `ext_base` e o `periph_base` de `generate.vhdl` continuam a valer só para o pacote do mapa, com a janela da plataforma como padrão. O `CACHE_WINDOW_BITS` nunca passa de `address_bits`.

### 9.3. Validações

Cada validação é um problema `platform` antes de gerar e no `check-memory-map`, com o nome do campo e a causa na mensagem.

| Regra | Condição de rejeição |
| :--- | :--- |
| V-A1 | `address_bits` não é inteiro ou está fora de 16 a 64 |
| V-A2 | `address_bits` acima de 32 com um perfil que não é `rv64` |
| V-A3 | Uma região (`base + size`) passa de $2^{\text{address\_bits}}$ bytes |
| V-A4 | Uma região passa da janela de periféricos, a base de um periférico não é a janela com `id << (address_bits - 4)`, ou esse deslocamento cai fora do espaço |
| V-A5 | `address_bits` abaixo de `xlen` sem `has_access_faults` no perfil (o acesso acima da janela precisa gerar falha de acesso) |
| V-A6 | `boot.entry` ou `boot.wait_restart` fora de $2^{\text{address\_bits}}$ |

A V-A5 só é conferida quando o perfil é resolvido, o que o `generate-memory-map` e o `check-memory-map` fazem sempre que `address_bits` é menor que `xlen`.

### 9.4. Periféricos por deslocamento, id e padding

Cada entrada de `peripherals` dá o endereço por `base` (absoluto) ou por `offset` (em bytes, a partir da base da janela de periféricos), uma das duas e nunca as duas. O `id` é opcional, e o `padding` reserva bytes logo depois do `size`, dentro do slot. Com `offset` o mesmo YAML vale para qualquer `address_bits`.

```yaml
address_bits: 32
peripherals:
  - {name: UART,  offset: 0x40000000}                           # id 4, derivado
  - {name: PLIC,  offset: 0x70000000, size: 4M, padding: 4M}    # slot 7, 4 MiB de padding
  - {name: CLINT, base: 0xE0000000, id: 6}                      # forma absoluta, como antes
```

| Campo | Significado |
| :--- | :--- |
| `offset` | Deslocamento da entrada na janela de periféricos. O endereço é a janela mais o `offset` |
| `base` | Endereço absoluto, que precisa estar na janela ou acima dela. O Tools o converte para `offset` |
| `id` | Índice do slot, de 0 a 7. Ausente, vale $\lfloor \text{offset} / 2^{\text{address\_bits} - 4} \rfloor$. Presente, precisa ser o slot do `offset` |
| `size` | Bytes que o periférico decodifica |
| `padding` | Bytes reservados depois do `size`. Ausente, vale o resto do slot de $2^{\text{address\_bits} - 4}$ bytes |

| Regra | Condição de rejeição |
| :--- | :--- |
| V-P1 | A entrada não tem exatamente um entre `base` e `offset`, ou o `base` está abaixo da janela |
| V-P2 | O `id` dado não é o slot do `offset` |
| V-P3 | O `size` mais o `padding` passam do fim do slot |
| V-P4 | Dois periféricos ocupam os mesmos bytes (`size` mais `padding`) |

A granularidade do mapa de periféricos é o slot: o decodificador do núcleo aceita um endereço da janela quando o bit do slot está em `PERIPH_SLOTS`, e o periférico decodifica só os bits baixos. O padding é registrado como área reservada, sem decodificação própria, então um acesso a ele tem o tratamento de qualquer endereço de um slot ocupado, e só um slot sem periférico gera falha de acesso.

Os símbolos dos `checks` ganham `<NOME>.offset`. Uma entrada que usa `offset` ou `padding` ganha no pacote do mapa as constantes `<NOME>_OFFSET`, `<NOME>_SIZE` (zero sem `size`) e `<NOME>_PAD`, em 32 bits como a `<NOME>_BASE`, e um valor que não cabe em 32 bits é recusado. As entradas só com `base` e `id` não ganham nada, e o `config_pkg` não as traz, para manter o texto do pacote padrão do Common-Components.

## 10. O `config_pkg`

### 10.1. Conteúdo

O `config_pkg` é o pacote VHDL de constantes de uma plataforma, escrito a partir do `platform.yaml`. Tem o contrato do pacote padrão do Common-Components (`src/config_pkg.vhd`), com o mesmo nome de unidade, as mesmas constantes, tipos e funções, e só os valores mudam, então a versão gerada ocupa o lugar dele na lista de fontes. Com os valores padrão (RV32IM, 32 bits de endereço, sem periféricos) o texto é idêntico ao do Common-Components, exceto o cabeçalho de geração. É um pacote de constantes, e não genérico, porque o Quartus Lite recusa o pacote genérico.

| Grupo | Constantes |
| :--- | :--- |
| Base e larguras | `IS_64`, `IS_BASE_E`, `ADDR_BITS`, `XLEN`, `REG_BITS`, `NUM_REGS` e os subtipos `word_t`, `reg_t`, `addr_t` e `map_addr_t` |
| Extensões e caches | Uma `HAS_<EXTENSÃO>` por chave do perfil (`HAS_M` a `HAS_ACCESS_FAULTS`), `HAS_ICACHE` e `HAS_DCACHE` |
| Memória | `BOOT_MEMORY_BITS`, o mapa em bytes no tipo `map_addr_t` (`ROM_BASE`, `ROM_END`, `RAM_BASE`, `RAM_END`, `EXT_BASE`, `PERIPH_BASE`), `ROM_EXTERNAL`, `RAM_EXTERNAL` e `CACHE_WINDOW_BITS` |
| Periféricos | Uma `HAS_<PERIFÉRICO>` para `UART`, `UART_PINS`, `UART_JTAG`, `TIMER`, `GPIO`, `DISPLAY`, `SWITCHES`, `KEYS`, `CLINT`, `PLIC` e `FLASH_CTRL` |
| Compostas | `HAS_MULDIV` (`HAS_M or HAS_ZMMUL`), `HAS_ANY_COUNTER` (`HAS_ZICNTR or HAS_ZIHPM`) e `HAS_SSCOF` (`HAS_SSCOFPMF and HAS_ZIHPM and HAS_INTERRUPTS`) |
| Funções | `isa_string`, o texto da ISA (`rv32im_zicsr_zicntr`), e `check_isa`, que falha na elaboração se uma dependência entre constantes não vale |

O `map_addr_t` é `unsigned(ADDR_BITS downto 0)`, com um bit a mais para representar o fim exclusivo $2^{\text{ADDR\_BITS}}$. Cada endereço sai como literal hexadecimal com os dígitos que `ADDR_BITS` pede (oito com 32 bits), de modo que a largura vale também abaixo e acima de 32 bits. `HAS_<PERIFÉRICO>` é verdadeira quando o nome está em `peripherals`, e a `UART` vale como `HAS_UART_JTAG` quando `console` é `jtag` e como `HAS_UART_PINS` quando `console` é `pins`. `ROM_EXTERNAL` e `RAM_EXTERNAL` dizem que a memória é alcançada pela porta do núcleo (externa ou atrás de cache), e têm os valores de `ROM_VIA_PORT` e `RAM_VIA_PORT` do pacote do mapa. A `HAS_E` do pacote do mapa é a `IS_BASE_E` daqui.

A `check_isa` confere que os contadores, as interrupções e as falhas de acesso têm `Zicsr`, que a `Sscofpmf` tem `Zihpm` e interrupções, que `ADDR_BITS` está de 16 a 64 e acima de 32 só com `IS_64`, e a ordem da `BOOT_MEMORY`, da ROM, da RAM, da janela externa e da janela de periféricos dentro de $2^{\text{ADDR\_BITS}}$. As entidades a chamam uma vez, num `if check_isa generate`.

### 10.2. Gerar junto com o mapa

A chave `generate.config_pkg` pede o arquivo, e o `generate-memory-map` o escreve (e o `--check` o compara) com os demais.

```yaml
generate:
  vhdl: {path: rtl/map_pkg.vhd, package: map_pkg, rom: FLASH, ram: RAM}
  config_pkg: {path: rtl/config_pkg.vhd}
```

Uma plataforma sem a chave não gera o pacote, e seus arquivos não mudam.

### 10.3. Divisão com o pacote do mapa

Nesta etapa o `config_pkg` entra ao lado do pacote do mapa, que não perde nenhuma constante. As constantes que os dois trazem têm de concordar.

| Constante do `*_map_pkg` | Constante do `config_pkg` |
| :--- | :--- |
| `HAS_E` | `IS_BASE_E` |
| `HAS_<EXTENSÃO>`, `HAS_ICACHE`, `HAS_DCACHE`, `BOOT_MEMORY_BITS`, `CACHE_WINDOW_BITS` | A mesma |
| `ROM_VIA_PORT`, `RAM_VIA_PORT` | `ROM_EXTERNAL`, `RAM_EXTERNAL` |
| `ROM_BASE_KIB`, `ROM_END_KIB`, `RAM_BASE_KIB`, `RAM_END_KIB`, `EXT_BASE_KIB`, `PERIPH_BASE_KIB` | `ROM_BASE`, `ROM_END`, `RAM_BASE`, `RAM_END`, `EXT_BASE`, `PERIPH_BASE`, em bytes |

Só o pacote do mapa tem `BOOT_MEMORY_SIZE_BYTES`, as `*_STORAGE_BYTES`, `RAM_LAST_PAGE`, os tamanhos das caches, `ROM_VIA_PORT`, `RAM_VIA_PORT`, `<NOME>_BASE` e `<NOME>_ID` de cada periférico e as constantes do CLINT, do PLIC e do clock da SDRAM. Só o `config_pkg` tem a base e as larguras, os tipos, as compostas, `HAS_<PERIFÉRICO>` e as funções, e o pacote do mapa tem também `PERIPH_SLOTS`. Um pacote do mapa não escreve um valor em KiB que não cabe num `natural`, nem a última página da RAM acima de 32 bits.

Quando a plataforma pede os dois arquivos, o `check-memory-map` lê os dois no disco e falha com `config-pkg` para um arquivo ausente ou para uma constante com valores diferentes nos dois.

### 10.4. Variantes para a prova formal

O `generate-config-pkg` escreve o pacote de uma plataforma ou de uma variante dela, sem precisar de `--config`.

```bash
uv run riscv-tools --root <projeto> generate-config-pkg --platform src/platform/platform.yaml
uv run riscv-tools --root <projeto> generate-config-pkg --platform src/platform/platform.yaml \
    --set IS_64=true --set ADDR_BITS=40 --output formal/config_rv64.vhd
```

| Opção | Efeito |
| :--- | :--- |
| `--platform` | O `platform.yaml` de que o pacote sai |
| `--set NOME=VALOR` | Troca `IS_64`, `IS_BASE_E` ou uma `HAS_*` (`true` ou `false`) ou `ADDR_BITS` (inteiro). Repetível |
| `--output` | Arquivo a escrever. Sem ele, o pacote vai para a saída padrão |

A variante é validada como uma plataforma própria, com V-A1 a V-A6 para o `ADDR_BITS` e o `IS_64` dela, e os periféricos vão para a janela da nova largura. Um nome que não é constante do pacote é um erro. O cabeçalho do arquivo lista a variante.

### 10.5. Lista de fontes

O `sources` mantém um só `config_pkg.vhd` na lista. Quando o arquivo do Common-Components e o gerado da plataforma aparecem, fica o gerado, na posição do padrão, de modo que toda unidade que o usa vem depois dele (ver [sources](sources.md)).

### 10.6. Plataformas que precisam declarar mais

Algumas plataformas precisam de uma declaração a mais para que o `config_pkg` gerado reflita a escolha delas.

| Caso | O que declarar |
| :--- | :--- |
| Interrupções sem `Zicsr` no perfil padrão (a `check_isa` falha na elaboração) | Gerar a variante com `--set HAS_ZICSR=true`, ou ligar o `Zicsr` no perfil |
| Uma `UART` cuja ligação (pinos ou JTAG) importa | `console: pins` ou `console: jtag`, ou os nomes de periférico `UART_PINS` e `UART_JTAG`. Sem isso só `HAS_UART` vale |
| `PERIPH_SLOTS` | Continua só no pacote do mapa, que o escreve a partir de `peripherals` |
| Largura de endereço abaixo de 26 bits com caches | `CACHE_WINDOW_BITS` nunca passa de `address_bits`, então a janela da tag é o espaço inteiro |

## 11. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_memory_map.py::test_evaluate_number_notations` | Hex, VHDL, `K`, sufixo `u` e aritmética. |
| `tests/test_memory_map.py::test_evaluate_symbols_and_log2` | Símbolos em expressões, `log2`/`clog2`, e `log2` rejeitando não potências de dois. |
| `tests/test_memory_map.py::test_evaluate_rejects_unknown_symbol_inexact_division_and_code` | Símbolo desconhecido, divisão inexata e código arbitrário são rejeitados. |
| `tests/test_memory_map.py::test_symbols_flattens_regions_reserved_boot_and_peripherals` | A tabela de símbolos. |
| `tests/test_memory_map.py::test_the_reference_platform_is_consistent` | Um mapa consistente não tem problemas. |
| `tests/test_memory_map.py::test_validate_platform_reports_an_inconsistent_map` | Sobreposições, reservado fora da RAM, entradas de boot e ids de periférico errados. |
| `tests/test_memory_map.py::test_check_passes_when_every_copy_agrees` | Cinco cópias em cinco formatos concordam. |
| `tests/test_memory_map.py::test_check_fails_when_one_copy_diverges` | Alterar qualquer cópia faz falhar exatamente o seu check. |
| `tests/test_memory_map.py::test_check_reports_every_divergent_match_of_one_pattern` | Cada casamento divergente é reportado. |
| `tests/test_memory_map.py::test_check_fails_when_a_copy_no_longer_matches_the_pattern` | Uma cópia reformatada é notada. |
| `tests/test_memory_map.py::test_check_fails_on_a_missing_file_unless_optional` | Arquivo ausente falha, salvo `optional`. |
| `tests/test_memory_map.py::test_check_stops_at_an_inconsistent_map` | Nenhuma cópia é lida se o próprio mapa é inconsistente. |
| `tests/test_memory_map.py::test_load_platform_rejects_a_non_mapping` | Um arquivo que não é mapeamento é rejeitado. |
| `tests/test_memory_map.py::test_cmd_check_memory_map_exit_status` | O comando imprime OK, ou sai com 1 listando as divergências. |
| `tests/test_peripheral_offsets.py` | `offset` e `base` dão o mesmo mapa, o `id` derivado, a mesma `offset` com outro `address_bits`, uma rejeição para cada V-P1 a V-P4 e as constantes `_OFFSET`, `_SIZE` e `_PAD` só nas entradas relativas. |
| `tests/test_address_bits.py` | O campo `address_bits` e a janela derivada, uma rejeição para cada V-A1 a V-A6, a janela fixa por `periph_window`, `resolve` com os perfis `rv64`, o `--profile` e as chaves novas do `config.yaml`. |
| `tests/test_config_pkg.py` | O `config_pkg` para 32, 24 e 40 bits, a base E, as variantes e o que elas recusam, a UART por `console`, a escrita com o mapa e o `--check`, a coerência entre os dois pacotes, o comando e a prova de que o pacote do mapa e o `config_pkg` do DE0-CV não mudam. |
| `tests/test_generate_memory_map.py` | Specs, linker script e pacote VHDL saem do mapa; `--check` pega arquivo ausente ou editado; endereço fora de KiB, região acima da janela dos periféricos e mapa inconsistente são rejeitados; o comando escreve e confere. |
| `tests/test_interrupts.py` | O pacote traz `HAS_INTERRUPTS`, `CLOCK_HZ`, `MTIME_HZ` e `CLINT_TICK_CYCLES`, o cabeçalho traz os registradores do CLINT e a taxa do `mtime`, e uma seção inconsistente (taxa, CLINT ausente, perfil sem as interrupções) é rejeitada. |
| `tests/test_memory_choice.py` | A seção `memory` e a opção `--memory` geram as 16 combinações como 16 pacotes diferentes, as constantes e os parâmetros da simulação saem da escolha, e as regras V1 a V5, V7 e V10 falham com mensagem clara. |
| `tests/test_config_from_platform.py` | As chaves de `memory`, o ambiente do `tohost` e do `stdout` e as larguras de endereço saem do mapa, e o mapa vale mais que o arquivo e os seus `extends`. |

## 12. Uso

```bash
uv run riscv-tools --root <projeto> check-memory-map --platform platforms/internal-mem.yaml
```

Não precisa de `--config`. Status 1 e uma linha `MISMATCH` por divergência quando uma cópia diverge; feito para o CI.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
