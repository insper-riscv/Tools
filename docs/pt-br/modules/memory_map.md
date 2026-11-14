# `memory_map`

Confere que todas as cópias escritas à mão do mapa de memória de uma plataforma concordam. O mapa (bases e tamanhos das regiões, as palavras que a memória de boot reserva no topo da RAM, os pontos de entrada do boot, as janelas dos periféricos) é necessário em muitos arquivos: flags do linker, memória de boot, runtime C, VHDL, IPs do Quartus, o `config.yaml` do projeto. Cada cópia só é notada quando diverge na placa. Um arquivo YAML, a plataforma, é a fonte da verdade; este módulo lê cada cópia e reporta toda divergência.

## 1. Configuração

Sem seção no `config.yaml`: o arquivo da plataforma se descreve sozinho e é passado com `--platform`.

```yaml
memory:                       # o mapa em si: três blocos de nomes fixos
  boot:
    base: 0x0
    size: 2K
  instructions:
    - type: onchip
      base: 0x800
      size: 30K
  data:
    - type: onchip
      base: 0x8000
      size: 160K
reserved:                     # palavras no topo dos dados
  stdout:
    base: 0x2FBE0
    size: 1K+8
  tohost:
    base: 0x2FFF0
    size: 16
boot:
  entry: 0x800
  wait_restart: 0x100
peripherals:                  # um bloco por nome, na ordem dos índices
  GPIO:
    base: 0xA0000000
    size: 64
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

- **Símbolos** em `expect`: `<REGIÃO>.base|size|end|words`, `<reservado>.base|size|end`, `boot.entry|wait_restart`, `<PERIFÉRICO>.base|size|window|index`.
- **Números** aceitam hexadecimal, decimal, VHDL (`16#800#`), sufixos (`30K`, `0x800u`) e `+ - * /` (divisão exata), além de `log2()` (exato) e `clog2()` (arredonda para cima, para larguras de endereço).
- Um check cujo padrão não casa nada **falha** ("a cópia mudou de lugar"); `optional: true` ignora um arquivo ausente. Um padrão com vários casamentos precisa concordar em todos.
- Antes de ler as cópias, o próprio mapa é validado: regiões e palavras reservadas não se sobrepõem, as reservadas ficam dentro de uma região RAM, `boot.entry` está numa região executável, `boot.wait_restart` está na primeira região, a janela de cada periférico está alinhada, cabe no espaço e não se sobrepõe a outra janela nem a uma região, e a BOOT_MEMORY, a FLASH e a RAM estão em ordem (ver a seção 9).

## 2. Gerar os arquivos do mapa

O mesmo YAML pode dizer, na seção `generate`, quais arquivos saem dele, de modo que nenhuma cópia do mapa precise ser escrita à mão.

| Chave | Arquivo gerado | Conteúdo |
| :--- | :--- | :--- |
| `specs` | Arquivo de specs do GCC | As flags do linker: `__flash`, `__flash_size`, `__ram`, `__ram_size` e `rv32_wait_restart`. A RAM do linker termina onde começa a palavra reservada `ram_limit`; com `cxx: true`, o arquivo também liga os objetos de C++ (ver "C++ na plataforma" abaixo) |
| `boot_ld` | Linker script da memória de boot | A memória `boot_memory` na primeira região e o `RESET_RESERVED` de `boot.wait_restart` |
| `runtime` | Cabeçalho do runtime (`.h`, também incluído por `.S`) | `RV32_RAM_END` (fim da RAM `ram`), `RV32_TOHOST_ADDR`, `RV32_FROMHOST_ADDR` e `RV32_STDOUT_BASE`, das faixas `reserved` que o mapa tem, `RV32_BOOT_ENTRY` (para onde a memória de boot salta) e `RV32_<NOME>_BASE` de cada periférico; o runtime em C e em assembly (`_exit.c`, `stdio.c`, `boot_memory.S`, `spike_exit.S`) usa esses nomes no lugar de endereços escritos à mão |
| `syscalls` | Arquivo C com as chamadas de sistema da `libstdc++` | `getentropy`, `read`, `open` e `close`, cada uma devolvendo -1 com `errno = ENOSYS`. Só vale com `cxx: true` em algum arquivo de specs, e não colide com o `_exit.c` nem com o `stdio.c` |
| `config_pkg` | Pacote VHDL de constantes da plataforma | O `config_pkg` da seção 10, ao lado do pacote do mapa |
| `vhdl` | Pacote VHDL | As constantes `BOOT_MEMORY_BITS`, `BOOT_MEMORY_SIZE_BYTES`, `FLASH_BASE_KIB`, `FLASH_END_KIB`, `FLASH_STORAGE_BYTES`, `RAM_BASE_KIB`, `RAM_END_KIB`, `RAM_STORAGE_BYTES` e `RAM_LAST_PAGE`, as flags `FLASH_ON_BUS` e `RAM_ON_BUS` (de `generate.vhdl` ou da seção `memory`), as constantes das caches da seção `memory`, `PERIPH_COUNT`, `STRICT_PERIPH`, as tabelas `PERIPH_BASES` e `PERIPH_MASKS` e, de cada periférico, `<NOME>_BASE` e `<NOME>_INDEX` |

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

`FLASH_STORAGE_BYTES` e `RAM_STORAGE_BYTES` são a menor potência de dois que cobre o fim da FLASH e o tamanho da RAM, e `RAM_LAST_PAGE` são os bits 31:12 da última página de 4 KiB da RAM.

Os limites do pacote VHDL são os genéricos do `core`, em KiB, então um endereço que não é múltiplo de 1 KiB é um erro. O mapa é validado antes de gerar, e um mapa inconsistente não gera nada.

```bash
uv run riscv-tools --root <projeto> generate-memory-map --platform src/platform/platform.yaml
uv run riscv-tools --root <projeto> generate-memory-map --platform src/platform/platform.yaml --check
```

Com `--check` nada é escrito, e o comando sai com status 1 se um arquivo faltar ou estiver diferente do que o mapa geraria. Não precisa de `--config`.

### 2.1. C++ na plataforma

Um programa C++ precisa de duas coisas a mais do que um C no `rv32im-fpga.specs`.

1. `cxx: true` na seção `specs` (ou numa entrada de `bank_specs`) gera o arquivo com `*startfile: crt0-hosted%O%s crtbegin%O%s` e `*endfile: crtend%O%s`. O `picolibc.specs` deixa os dois objetos de fora, então nada registraria os quadros de desenrolamento e um `throw` falharia. Como o `*startfile` é redefinido, a opção `--crt0=` do `picolibc.specs` deixa de valer, e por isso o arquivo já escolhe o `crt0-hosted`. O arquivo também faz do `picolibcpp.ld` o linker script padrão, por um `*self_spec` que só age quando o comando não traz `-T`. Sem `cxx`, o arquivo é o de C, byte a byte.
2. `syscalls: {path: ...}` escreve o arquivo C com `getentropy`, `read`, `open` e `close`, que a `libstdc++` pede e a picolibc não dá. O arquivo entra em `paths.sources` do projeto, ao lado do `_exit.c` e do `stdio.c`.

```yaml
generate:
  specs: {path: runtime/rv32im-fpga.specs, rom: FLASH, ram: RAM, ram_limit: stdout, cxx: true}
  syscalls: {path: runtime/syscalls.c}
```

O `toolchain.cxx` do projeto liga o lado do compilador (veja [`compiler`](compiler.md)). A `libatomic` está fora do escopo: um `std::atomic` de 8 bytes, e qualquer um numa variante sem a extensão A, fica sem definição.


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

## 4. O núcleo da plataforma

O `platform.yaml` não tem nome de perfil. Ele descreve o núcleo no bloco `core`, e o Tools infere dele o perfil da especificação do Core, que a plataforma localiza em `profiles:`, um caminho relativo ao `platform.yaml` (o `profiles/matrix.yaml` do Core).

```yaml
core:
  type: 32          # 32 ou 64 (RV32 ou RV64)
  base: I           # I ou E (32 ou 16 registradores)
  extensions:       # ou `extensions: []`
    - M
    - Zicsr
    - Zicclsm
    - Zicntr
    - Zihpm
    - Zifencei
    - Zimop
    - Zicond
    - Zihintntl
    - Zihintpause
    - Interrupts
    - Sscofpmf
    - AccessFaults
profiles: ../../../Core/profiles/matrix.yaml
```

As chaves são `type`, `base` e `extensions`, em minúsculas, e os nomes das extensões não diferenciam maiúsculas. O módulo `riscv_tools.memory_map.core_profile` faz a inferência.

| Regra | Efeito |
| :--- | :--- |
| Extensões da matriz (`M`, `Zmmul`, `Zicsr`, `Zicntr`, `Zihpm`, `Zifencei`, `Zicclsm`, `Zimop`, `Zicond`) | Escolhem o perfil `rv<type><base>` com as extensões na ordem canônica do nome, como `rv32im_zicclsm_zicntr_zihpm_zifencei` |
| Extensões que a matriz não lista (`Zihintntl`, `Zihintpause`, `Interrupts`, `Sscofpmf`, `AccessFaults`; também `Zimop` e `Zicond` se a matriz não as lista) | São os extras, ligados por cima do perfil |
| Normalização | `M` implica `Zmmul`, e `Zicntr` e `Zihpm` implicam `Zicsr`. Listar `Zicsr` junto de `Zicntr` ou `Zihpm` é aceito, e o nome inferido não o cita |
| Erro | Extensão desconhecida ou repetida; combinação que a matriz recusa (`M` com `Zmmul`); `type: 64` sem base `rv64` na matriz; `isa` no lugar de `base` ("a chave se chama base"); chave desconhecida ou ausente |
| Migração | `profile:` e `extras:` são recusados, com a mensagem do bloco que os substitui: `profile: rv32em_zicntr` vira `type` 32, `base` E e `extensions` M, Zicntr |

Do perfil saem:

| Saída | Conteúdo |
| :--- | :--- |
| Pacote VHDL | `IS_E` (verdadeiro no RV32E) e um `HAS_<EXTENSÃO>` booleano por extensão do núcleo (`HAS_M`, `HAS_ZMMUL`, `HAS_ZICSR`, `HAS_ZICNTR`, `HAS_ZIHPM`, `HAS_ZIMOP`, `HAS_ZICOND`, `HAS_ZIHINTNTL`, `HAS_ZIHINTPAUSE`, `HAS_ZIFENCEI`, `HAS_ZICCLSM`, `HAS_INTERRUPTS`, `HAS_SSCOFPMF`, `HAS_ACCESS_FAULTS`) |
| `config.yaml` | `isa.base`, que escolhe o `-march` e o `-mabi` dos programas e da memória de boot (`rv32e` com `ilp32e`, os demais com `ilp32`), e o `sim.config_pkg`, o texto do `config_pkg` do perfil que o runner compila no lugar do `config_pkg.vhd` das fontes (a base e as extensões do núcleo são constantes desse pacote, não generics do topo) |

`--profile NOME`, opção global do `riscv-tools`, troca só a parte do perfil da matriz, sem editar a plataforma, para rodar a mesma plataforma sobre vários perfis numa matriz de testes. As extensões que a matriz não lista continuam ligadas. Vale para o `generate-memory-map` (escreve o pacote daquele perfil), para o `platform sync` e para todo comando que lê a configuração. Um nome que a especificação não lista é rejeitado antes de qualquer coisa rodar.

A `Sscofpmf` exige `Zihpm` e `Interrupts`, e a geração falha sem eles. Toda chave que nem o perfil nem os extras ligam sai `false` no pacote. Uma plataforma sem `profiles:` guarda só o nome do perfil, na ordem da matriz do Core.

```bash
uv run riscv-tools --root <projeto> --profile rv32em_zicsr generate-memory-map --platform src/platform/platform.yaml
```

## 5. As interrupções da plataforma

Uma plataforma com as interrupções de máquina liga a extensão `Interrupts` em `core` (o núcleo só as habilita se tiver `Zicsr`), lista o `CLINT` e, para as linhas externas, o `EXT_IRQ` entre os `peripherals`, e descreve o relógio na seção `interrupts`.

```yaml
core: {type: 32, base: I, extensions: [Zicsr, Interrupts]}
peripherals:
  - {name: CLINT,   base: 0xE0000000, size: 64K}
  - {name: EXT_IRQ, base: 0xF0000000, size: 16}
interrupts:
  clock_hz: 50000000   # relógio do domínio do núcleo e do CLINT
  mtime_hz: 1000000    # taxa com que o mtime do CLINT conta
```

O `mtime` do CLINT é um contador próprio, ajustado por `mtime_hz`, e é independente do CSR `time` da Zicntr, que o núcleo atende. Com `clocks.core` na plataforma o `clock_hz` é omitido e vale o relógio do núcleo arredondado para um número inteiro de ciclos por incremento; escrito, ele precisa ser esse valor. O `clock_hz` precisa ser múltiplo de `mtime_hz`, o perfil precisa ligar `has_interrupts`, e a lista `peripherals` precisa ter o `CLINT`; a ausência de qualquer um deles é um erro antes de gerar e no `check-memory-map`.

| Saída | Constantes |
| :--- | :--- |
| Pacote VHDL (`vhdl`) | `HAS_INTERRUPTS`, `CLOCK_HZ`, `MTIME_HZ` e `CLINT_TICK_CYCLES` (ciclos de relógio por incremento do `mtime`, o genérico `tick_cycles` do CLINT), além de `CLINT_BASE`, `CLINT_INDEX`, `EXT_IRQ_BASE` e `EXT_IRQ_INDEX` |
| Cabeçalho do runtime (`runtime`) | `RV32_CLINT_BASE`, `RV32_MSIP`, `RV32_MTIMECMP`, `RV32_MTIME` e `RV32_MTIME_HZ`, que o `FreeRTOSConfig.h` usa em `configMTIMECMP_BASE_ADDRESS`, `configMTIME_BASE_ADDRESS` e `configCPU_CLOCK_HZ` |

Os deslocamentos dos registradores dentro da janela de 64 KiB do CLINT seguem o leiaute da SiFive que o porte do FreeRTOS espera.

### 5.1. PLIC e fontes de interrupção

Uma plataforma com PLIC o lista em `peripherals` com um `size` (a janela que ele decodifica, potência de dois de pelo menos `0x200008` bytes) e o descreve em `interrupts`.

```yaml
peripherals:
  - {name: PLIC, base: 0xF0000000, size: 4M}
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

### 5.2. Temporizadores de uso geral

A plataforma pode ter qualquer quantidade de temporizadores. Cada um é uma entrada de `peripherals` com `kind: timer`, nome livre, `base` própria e `size` de pelo menos 32 bytes (os oito registradores).

```yaml
peripherals:
  TIMER0:
    kind: timer
    base: 0x80006000
    size: 64
  TIMER1:
    kind: timer
    base: 0x80006100
    size: 64
```

A entrada chamada `TIMER` sem `kind` também é um temporizador, então as plataformas com um só continuam como estão. Cada temporizador tem uma fonte própria no PLIC, e a lista `interrupts.sources` não precisa nomeá-lo.

| Situação | Número da fonte |
| :--- | :--- |
| O temporizador está em `interrupts.sources` | O que está escrito (não pode ser 1, 2, 3, 4 nem 6, as linhas fixas do SoC) |
| O temporizador não está em `sources` | O menor número a partir de 5 que nenhuma fonte usa e que não é linha fixa, na ordem de `peripherals` |

A regra só depende do arquivo, então as fontes dos outros periféricos não mudam de número com a quantidade de temporizadores.

| Saída | Constantes |
| :--- | :--- |
| Pacote VHDL (`vhdl`) | `<NOME>_BASE` e `<NOME>_INDEX` de cada um, `IRQ_<NOME>`, `TIMER_COUNT` e as tabelas `TIMER_INDICES` (o índice de cada um nas tabelas de janelas) e `TIMER_IRQ_IDS` (a fonte de cada um, 0 sem PLIC), vazias sem temporizador |
| Cabeçalho do runtime (`runtime`) | `RV32_<NOME>_BASE` e `RV32_IRQ_<NOME>` de cada um |
| Topo da placa (`board generate`) | `timer_indices => TIMER_INDICES` e `timer_irq_ids => TIMER_IRQ_IDS` no SoC, só quando há temporizador |

O `kind` é um entre `timer`, `gpio` e `seg_display` (a lista fica num só lugar, `memory_map/kinds.py`). O temporizador precisa de `size`, que um bloco `gpio` ou `seg_display` não pode ter (a janela vem dos grupos). Um `kind` desconhecido (V-P7), uma janela menor que 32 bytes (V-P8), um nome que não é identificador VHDL ou que repete em maiúsculas (V-P9) e uma fonte presa numa linha fixa (V-P10) são erros antes de gerar. O alinhamento e a sobreposição das janelas seguem as regras dos outros periféricos (V-P2, V-P4 e V-P5).

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

A seção `memory` do `platform.yaml` descreve as três memórias do núcleo em blocos de nomes fixos e escolhe, por plataforma, quatro coisas independentes, e das 16 combinações 9 são válidas. O `boot` é um bloco único (`base` 0 e `size`). `instructions` e `data` são listas de segmentos, e nesta fase cada uma tem exatamente um segmento; um segundo é recusado com "vários segmentos ainda não são suportados". O `boot` e as `instructions` são executáveis e os `data` não, e os nomes das regiões no pacote são fixos (`BOOT_MEMORY`, `FLASH` e `RAM`). O módulo `riscv_tools.memory_map.layout` lê o bloco.

```yaml
memory:
  boot:
    base: 0x00000000
    size: 4K
  instructions:
    - type: emulated
      base: 0x00001000
      size: 252K
      on_bus: true
      latency:
        first: 24
        next: 4
      sector_bytes: 4096
      cache:
        size_bits: 32768
  data:
    - type: sdram
      base: 0x40000000
      size: 64M
      on_bus: true
      cache:
        size_bits: 32768
```

| Campo do segmento | Tipo | Significado |
| :--- | :--- | :--- |
| `type` | `flash`, `sdram`, `sram`, `onchip` ou `emulated` | O que a memória é: um chip NOR, a SDRAM ou a SRAM da placa, blocos de memória do FPGA, ou blocos do FPGA com a latência de um chip (`emulated`) |
| `base`, `size` | endereço e tamanho | Onde o segmento fica; obrigatórios |
| `on_bus` | booleano | A memória é alcançada pelo barramento (`FLASH_ON_BUS` e `RAM_ON_BUS`) e não pela porta direta. Um tipo diferente de `onchip` exige `on_bus: true`. Vale nos dois segmentos ou em nenhum, e sem ele a escolha vem do `--memory` |
| `latency` | `first` e `next` | Só na memória `emulated`: ciclos do primeiro acesso e dos seguintes |
| `sector_bytes` | potência de dois | Setor de apagamento da FLASH emulada |
| `cache` | `size_bits` | Presente: existe a cache do segmento (de instruções em `instructions`, de dados em `data`); `size_bits` é potência de dois de pelo menos 256 |

As chaves antigas são recusadas com a migração: a lista `regions` (`BOOT_MEMORY`, `FLASH` e `RAM` viram `boot`, `instructions` e `data`, e `kind` e `exec` deixam de existir), `memory.rom` e `memory.ram` (viram os segmentos, com `external` virando `on_bus` e `backend` e `device` virando `type`) e `memory.icache` e `memory.dcache` (viram `cache` do segmento). A `peripherals` em lista também é recusada: ela é um mapa por nome, na ordem dos índices.

Os campos `rom_external` e `ram_external` de `generate.vhdl` saem de `on_bus`, e os dois juntos com ele são um erro.

### 7.1. Constantes geradas

O pacote VHDL ganha as constantes abaixo. `FLASH_ON_BUS` e `RAM_ON_BUS` dizem que a memória é alcançada pelo barramento, dentro ou fora do chip, e não pela porta direta do núcleo. Uma cache só existe sobre uma memória no barramento.

| Constante | Tipo | Valor |
| :--- | :--- | :--- |
| `FLASH_ON_BUS` | boolean | `memory.rom.external` |
| `RAM_ON_BUS` | boolean | `memory.ram.external` |
| `HAS_ICACHE` | boolean | `memory.icache.enabled` |
| `HAS_DCACHE` | boolean | `memory.dcache.enabled` |
| `ICACHE_SIZE_BITS` | positive | `memory.icache.size_bits`, ou 256 sem a cache |
| `DCACHE_SIZE_BITS` | positive | `memory.dcache.size_bits`, ou 256 sem a cache |
| `I_CACHE_WINDOW_BITS`, `D_CACHE_WINDOW_BITS` | natural | Menor largura de 26 a 29 tal que a FLASH e a RAM cabem cada uma numa janela alinhada de $2^{\text{largura}}$ bytes (26 é 64 MiB, 27 é 128 MiB), derivada das regiões; as duas valem o mesmo |

No `config.yaml` os valores chegam como `sim.parameters` com os nomes `ROM_EXTERNAL`, `RAM_EXTERNAL`, `HAS_ICACHE`, `HAS_DCACHE`, `ICACHE_SIZE_BITS` e `DCACHE_SIZE_BITS`, e com `CACHE_WINDOW_BITS` só quando passa de 26, e o topo de simulação precisa declarar os genéricos correspondentes. Sem `config.addr_widths` na plataforma, as larguras de endereço vêm da escolha, e saem a `boot_memory` e cada memória interna, já que uma memória externa é um chip dimensionado pelo próprio topo. Com `config.addr_widths` listado, a lista vale.

### 7.2. Validação

| Regra | Condição | Resultado |
| :--- | :--- | :--- |
| V1 | Os quatro booleanos existem e não há chave desconhecida | Erro |
| V2 | `size_bits` é potência de dois e vale pelo menos 256 | Erro |
| V3 | Com alguma cache, a FLASH e a RAM cabem cada uma numa janela alinhada de até 512 MiB (a tag das caches guarda os bits abaixo da janela) | Erro |
| V4 | Com a FLASH no barramento, o tamanho dela cabe na janela de 1024 KiB do roteador | Erro |
| V9 | Plataforma com periféricos | Nota |
| V10 | Com alguma cache, `reserved.fromhost` existe e está na última página de 4 KiB da RAM, a que a cache ignora | Erro |
| V-C1 | `icache.enabled` com `rom.external: false`: a cache de instruções exige `FLASH_ON_BUS` | Erro |
| V-C2 | `dcache.enabled` com `ram.external: false`: a cache de dados exige `RAM_ON_BUS` | Erro |

Das 16 combinações de `rom.external`, `ram.external`, `icache.enabled` e `dcache.enabled`, 9 são válidas e 7 são recusadas pela V-C1 e pela V-C2. FLASH no barramento sem cache de instruções é válida. A nota sai em `NOTE` no erro padrão do `generate-memory-map`, e os erros impedem a geração.

### 7.3. A opção `--memory`

`--memory`, opção global do `riscv-tools`, troca campos da seção `memory` sem editar a plataforma, para rodar a mesma plataforma sobre as combinações. O valor é uma lista de pares `chave=valor` separados por vírgula.

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

O campo de topo `address_bits` do `platform.yaml` é um inteiro de 16 a `XLEN` (o `type` do bloco `core`: 32 ou 64) com a largura do endereço físico. Ausente, vale 32, e nenhuma plataforma escrita para 32 bits precisa mudar. Um `type: 64` liga o `IS_64` do `config_pkg` e aceita de 16 a 64 bits, inclusive menos de 64.

```yaml
address_bits: 24      # opcional, 32 por padrão
core: {type: 32, base: I, extensions: [M]}
peripherals:          # base absoluta e size em bytes de registradores
  - {name: UART, base: 0xC00000, size: 16}
```

### 9.2. A janela de cada periférico

O núcleo só conhece a BOOT_MEMORY, a FLASH e a RAM, e todo endereço fora delas sai pela porta externa. Quem decodifica os periféricos é o interconector, por uma tabela com uma janela por periférico. A janela é derivada do `size`.

$$ \text{janela} = \max\left(16,\ 2^{\lceil \log_2 \text{size} \rceil}\right), \quad \text{o periférico } i \text{ responde quando } (\text{endereço} \wedge \text{máscara}_i) = \text{base}_i $$

A máscara de um periférico tem os bits do endereço acima da janela, então um periférico de 64 KiB com 32 bits de endereço tem a máscara `0xFFFF0000`. Não há janela fixa de periféricos, teto de quantidade nem identificador de slot, e a posição de cada periférico na lista `peripherals` é o `<NOME>_INDEX` dele nas tabelas.

### 9.3. Validações

Cada validação é um problema `platform` antes de gerar e no `check-memory-map`, com o nome do campo e a causa na mensagem.

| Regra | Condição de rejeição |
| :--- | :--- |
| V-A1 | `address_bits` não é inteiro ou está fora de 16 a 64 |
| V-A2 | `address_bits` maior que `XLEN` (32 com `type: 32`, 64 com `type: 64`), mensagem "ADDR_BITS maior que XLEN" |
| V-A3 | Uma região (`base + size`) passa de $2^{\text{address\_bits}}$ bytes |
| V-A4 | A janela de um periférico passa de $2^{\text{address\_bits}}$ bytes |
| V-A5 | `address_bits` abaixo de `xlen` sem `has_access_faults` no perfil (o acesso acima da janela precisa gerar falha de acesso) |
| V-A6 | `boot.entry` ou `boot.wait_restart` fora de $2^{\text{address\_bits}}$ |
| V-M1 | A BOOT_MEMORY (a primeira região) não começa no endereço 0 |
| V-M2 | A BOOT_MEMORY termina depois do começo da FLASH |
| V-M3 | A FLASH não tem tamanho positivo |
| V-M4 | A FLASH termina depois do começo da RAM |
| V-M5 | A RAM não tem tamanho positivo ou passa de $2^{\text{address\_bits}}$ bytes |

A V-A5 só é conferida quando o perfil é resolvido, o que o `generate-memory-map` e o `check-memory-map` fazem sempre que `address_bits` é menor que `xlen`. As regras V-M valem quando a plataforma nomeia a FLASH e a RAM em `generate.vhdl` ou em `config`.

### 9.4. Periféricos por base e tamanho

Cada entrada de `peripherals` dá o endereço absoluto `base` e o `size`, os bytes de registradores do periférico. A `base` precisa ser múltipla da janela.

```yaml
address_bits: 32
peripherals:
  - {name: DISPLAY,  base: 0x80001000, size: 4}
  - {name: SWITCHES, base: 0x80003000, size: 64}
  - {name: CLINT,    base: 0xE0000000, size: 64K}
```

| Campo | Significado |
| :--- | :--- |
| `base` | Endereço absoluto do começo da janela, alinhado ao tamanho dela |
| `size` | Bytes de registradores. O que sobra da janela depois deles é o antigo padding |
| `id`, `offset`, `padding` | Recusados com a mensagem de migração: a entrada dá a `base` que o `id` dava (`id: 5` vira `base: 0xD0000000`) e o `size` |

| Regra | Condição de rejeição |
| :--- | :--- |
| V-P1 | A entrada não tem `base` e `size`, o `size` não é positivo, ou traz `id`, `offset` ou `padding` |
| V-P2 | A `base` não é múltipla da janela |
| V-P4 | Duas janelas de periféricos se sobrepõem |
| V-P5 | A janela de um periférico se sobrepõe a uma região |
| V-P6 | O campo de topo `periph_window`, ou o `ext_base` ou o `periph_base` de `generate.vhdl`, que o núcleo não conhece mais |
| V-P7 | O `kind` de um periférico não é `timer`, `gpio` nem `seg_display` |
| V-P8 | Um temporizador tem `size` menor que 32 bytes |
| V-P9 | O nome de um periférico não é identificador VHDL ou repete em maiúsculas |
| V-P10 | Um temporizador está preso numa linha fixa do SoC (1, 2, 3, 4 ou 6) |
| V-S1 | A chave `strict_periph`, quando dada, não é um booleano |

A chave `strict_periph` da plataforma, verdadeira quando ausente, é uma política do interconector: com ela ligada, um acesso ao que sobra da janela depois do `size` termina com erro, e com `strict_periph: false` esse acesso lê zero e ignora a escrita. Ela sai como `STRICT_PERIPH` no pacote do mapa, e não no `config_pkg`.

Os símbolos dos `checks` de um periférico são `<NOME>.base`, `<NOME>.size`, `<NOME>.window` e `<NOME>.index`. O pacote do mapa ganha, de cada periférico, `<NOME>_BASE` (do tipo `addr_t`) e `<NOME>_INDEX`, e as tabelas abaixo.

| Constante | Tipo | Valor |
| :--- | :--- | :--- |
| `PERIPH_COUNT` | natural | Quantidade de entradas de `peripherals` |
| `STRICT_PERIPH` | boolean | A chave `strict_periph` |
| `periph_addr_array_t` | tipo | `array (natural range <>) of addr_t` |
| `PERIPH_BASES` | `periph_addr_array_t(0 to PERIPH_COUNT - 1)` | A `base` de cada periférico, indexada por `<NOME>_INDEX` |
| `PERIPH_MASKS` | `periph_addr_array_t(0 to PERIPH_COUNT - 1)` | A máscara da janela de cada periférico |


O pacote VHDL ganha as constantes abaixo. `FLASH_ON_BUS` e `RAM_ON_BUS` dizem que a memória é alcançada pelo barramento, dentro ou fora do chip, e não pela porta direta do núcleo. Uma cache só existe sobre uma memória no barramento.

| Constante | Tipo | Valor |
| :--- | :--- | :--- |
| `FLASH_ON_BUS` | boolean | `memory.rom.external` |
| `RAM_ON_BUS` | boolean | `memory.ram.external` |
| `HAS_ICACHE` | boolean | `memory.icache.enabled` |
| `HAS_DCACHE` | boolean | `memory.dcache.enabled` |
| `ICACHE_SIZE_BITS` | positive | `memory.icache.size_bits`, ou 256 sem a cache |
| `DCACHE_SIZE_BITS` | positive | `memory.dcache.size_bits`, ou 256 sem a cache |
| `I_CACHE_WINDOW_BITS`, `D_CACHE_WINDOW_BITS` | natural | Menor largura de 26 a 29 tal que a FLASH e a RAM cabem cada uma numa janela alinhada de $2^{\text{largura}}$ bytes (26 é 64 MiB, 27 é 128 MiB), derivada das regiões; as duas valem o mesmo |

No `config.yaml` os valores chegam como `sim.parameters` com os nomes `ROM_EXTERNAL`, `RAM_EXTERNAL`, `HAS_ICACHE`, `HAS_DCACHE`, `ICACHE_SIZE_BITS` e `DCACHE_SIZE_BITS`, e com `CACHE_WINDOW_BITS` só quando passa de 26, e o topo de simulação precisa declarar os genéricos correspondentes. Sem `config.addr_widths` na plataforma, as larguras de endereço vêm da escolha, e saem a `boot_memory` e cada memória interna, já que uma memória externa é um chip dimensionado pelo próprio topo. Com `config.addr_widths` listado, a lista vale.

### 7.2. Validação

| Regra | Condição | Resultado |
| :--- | :--- | :--- |
| V1 | Os quatro booleanos existem e não há chave desconhecida | Erro |
| V2 | `size_bits` é potência de dois e vale pelo menos 256 | Erro |
| V3 | Com alguma cache, a FLASH e a RAM cabem cada uma numa janela alinhada de até 512 MiB (a tag das caches guarda os bits abaixo da janela) | Erro |
| V4 | Com a FLASH no barramento, o tamanho dela cabe na janela de 1024 KiB do roteador | Erro |
| V5 | Região `exec` na RAM exige RAM e FLASH no barramento | Erro |
| V7 | Região `exec` na RAM atrás da cache de instruções exige Zifencei no perfil | Erro |
| V9 | Plataforma com periféricos | Nota |
| V10 | Com alguma cache, `reserved.fromhost` existe e está na última página de 4 KiB da RAM, a que a cache ignora | Erro |
| V-C1 | `icache.enabled` com `rom.external: false`: a cache de instruções exige `FLASH_ON_BUS` | Erro |
| V-C2 | `dcache.enabled` com `ram.external: false`: a cache de dados exige `RAM_ON_BUS` | Erro |

Das 16 combinações de `rom.external`, `ram.external`, `icache.enabled` e `dcache.enabled`, 9 são válidas e 7 são recusadas pela V-C1 e pela V-C2. FLASH no barramento sem cache de instruções é válida. A nota sai em `NOTE` no erro padrão do `generate-memory-map`, e os erros impedem a geração.
### 9.5. Blocos de GPIO e de display, com grupos

Um periférico com `kind: gpio` ou `kind: seg_display` é um bloco que reúne os pinos de um ou mais papéis da placa em grupos, cada grupo com o seu arquivo de registradores. O `size` não se escreve, porque a janela é derivada dos grupos.

```yaml
peripherals:
  LEDR:
    kind: gpio
    role: leds
    base: 0x80002000
    groups: solo
  KEY:
    kind: gpio
    role: keys
    base: 0x80004000
    groups: [[0, 1], [2, 3]]
  HEX:
    kind: seg_display
    base: 0x80005000
    groups: [[0, 1, 2, 3], [4, 5]]
```

| Campo | Significado |
| :--- | :--- |
| `kind` | `gpio` ou `seg_display` |
| `role` ou `roles` | Papel dos pinos (`leds`, `switches`, `keys`, `display`, `leds_green`, `gpio`, `ex_io`, `hsmc`); `roles: [a, b]` reúne os pinos de `a` e depois os de `b`. Um `seg_display` mostra só o papel `display`, e um `gpio` com `role: display` tem um pino por segmento (7 por dígito). Os papéis `gpio`, `ex_io` e `hsmc` têm direção livre, e um papel de vários grupos de sinais numera os pinos na ordem da lista (ver [board_schema](board_schema.md)) |
| `base` | Base do bloco, alinhada à janela |
| `groups` | `solo` (um grupo por pino), `all` (um grupo com todos), `pairs` ou `trios` (grupos de 2 ou 3 pinos seguidos, o último pode ser menor) ou uma lista de listas de índices de pino |

Os pinos de um papel são numerados de 0, e um pino que não está em nenhum grupo fica desligado. Cada grupo ocupa 64 bytes, então o bloco tem $64 G$ bytes e a janela é a menor potência de dois que os cobre, com no mínimo 16 bytes. A contagem de pinos e a polaridade de cada papel vêm do `io` do `board.yaml` de cada placa de `boards`, e o `gpio` tem a direção fixa do papel (saída em `leds`, `leds_green` e `display`, entrada em `switches` e `keys`).

| Regra | Condição de rejeição |
| :--- | :--- |
| G-0 | Um atalho que precisa dos pinos (`solo`, `pairs`, `trios`) sem `boards` ou sem o catálogo de placas |
| G-1 | Um índice de pino maior ou igual ao número de pinos dos papéis na placa |
| G-2 | Um pino repetido, em dois grupos ou duas vezes no mesmo |
| G-3 | Um grupo vazio ou com mais de 32 pinos |
| G-4 | A placa não tem um dos papéis do bloco |
| G-5 | `groups` que não é um atalho nem uma lista de listas de inteiros |
| G-6 | As placas de `boards` dão números de grupos diferentes ao mesmo bloco, e a janela diferiria |

Os pinos desligados saem em notas (`NOTE`) do `generate-memory-map`, e um papel `required` em `io` cujos blocos não têm grupo algum sai como aviso. O pacote do mapa ganha `<NOME>_BASE`, `<NOME>_INDEX` e as entradas das tabelas `PERIPH_BASES` e `PERIPH_MASKS` como nos outros periféricos, e o `memory_map.h` ganha `RV32_<NOME>_G<k>_BASE`, a base mais $64k$ bytes.

A chave `generate.platform_h` escreve o `rv32_platform.h` dos programas de teste a partir da plataforma: `RV32_RAM_BASE`, `RV32_RAM_END`, `RV32_STDOUT_BASE`, `RV32_TOHOST`, o `RV32_<NOME>_BASE` de cada periférico, os `RV32_<NOME>_G<k>_BASE`, as bancas da FLASH, `RV32_TICK_CYCLES` e as macros `RVMODEL_HALT_PASS` e `RVMODEL_HALT_FAIL`.

## 10. O `config_pkg`

### 10.1. Conteúdo

O `config_pkg` é o pacote VHDL de constantes de uma plataforma, escrito a partir do `platform.yaml`. Tem o contrato do pacote padrão do Common-Components (`src/config_pkg.vhd`), com o mesmo nome de unidade, as mesmas constantes, tipos e funções, e só os valores mudam, então a versão gerada ocupa o lugar dele na lista de fontes. Com os valores padrão (RV32I com Zicclsm, 32 bits de endereço, sem periféricos) o texto é idêntico ao do Common-Components, exceto o cabeçalho de geração e a janela das caches. É um pacote de constantes, e não genérico, porque o Quartus Lite recusa o pacote genérico.

| Grupo | Constantes |
| :--- | :--- |
| Base e larguras | `IS_64`, `IS_E`, `ADDR_BITS`, `XLEN`, `REG_BITS`, `NUM_REGS` e os subtipos `word_t`, `reg_t`, `addr_t` e `map_addr_t` |
| Sistema de memória | `HAS_ICACHE`, `HAS_DCACHE`, `FLASH_ON_BUS` e `RAM_ON_BUS` |
| Extensões | Uma `HAS_<EXTENSÃO>` por chave do perfil (`HAS_ZICCLSM` a `HAS_ZIHINTPAUSE`) |
| Memória | `BOOT_MEMORY_BITS`, `BOOT_MEMORY_BASE` e `BOOT_MEMORY_END` (de 0 a $2^{\text{BOOT\_MEMORY\_BITS}}$), `FLASH_BASE`, `FLASH_END`, `RAM_BASE` e `RAM_END` no tipo `map_addr_t`, e `I_CACHE_WINDOW_BITS` e `D_CACHE_WINDOW_BITS` |
| Compostas | `HAS_MULTIPLICATION` (`HAS_M or HAS_ZMMUL`), `HAS_ANY_COUNTER` (`HAS_ZICNTR or HAS_ZIHPM`) e `HAS_SSCOF` (`HAS_SSCOFPMF and HAS_ZIHPM and HAS_INTERRUPTS`) |
| Funções | `isa_string`, o texto da ISA (`rv32im_zicsr_zicntr`), e `check_isa`, que falha na elaboração se uma dependência entre constantes não vale |

O `map_addr_t` é `unsigned(ADDR_BITS downto 0)`, com um bit a mais para representar o fim exclusivo $2^{\text{ADDR\_BITS}}$. Cada endereço sai como `resize(unsigned'(x"..."), ADDR_BITS + 1)`, com os dígitos hexadecimais que `ADDR_BITS` pede (oito com 32 bits), de modo que a largura vale também abaixo e acima de 32 bits. `FLASH_ON_BUS` e `RAM_ON_BUS` dizem que a memória é alcançada pelo barramento, e são o `memory.rom.external` e o `memory.ram.external` da plataforma. As duas janelas das caches valem a largura da janela da tag da seção 7.1. O pacote não tem constantes dos periféricos do SoC (UART, display, chaves, botões, controlador da FLASH), nem `EXT_BASE`, `PERIPH_BASE` e `STRICT_PERIPH`, que ficam no pacote do mapa.

A `check_isa` confere que os contadores, as interrupções e as falhas de acesso têm `Zicsr`, que a `Sscofpmf` tem `Zihpm` e interrupções, que `ADDR_BITS` está de 16 a `XLEN` (o núcleo não tem MMU, então o endereço efetivo nunca passa de `XLEN` bits), que a cache de instruções exige `FLASH_ON_BUS` e a de dados exige `RAM_ON_BUS`, e a ordem da BOOT_MEMORY, da FLASH e da RAM dentro de $2^{\text{ADDR\_BITS}}$. As entidades a chamam uma vez, num `if check_isa generate`.

### 10.2. Gerar junto com o mapa

A chave `generate.config_pkg` pede o arquivo, e o `generate-memory-map` o escreve (e o `--check` o compara) com os demais.

```yaml
generate:
  vhdl: {path: rtl/map_pkg.vhd, package: map_pkg, rom: FLASH, ram: RAM}
  config_pkg: {path: rtl/config_pkg.vhd}
```

Uma plataforma sem a chave não gera o pacote, e seus arquivos não mudam.

### 10.3. Divisão com o pacote do mapa

O `config_pkg` fica ao lado do pacote do mapa. As constantes que os dois trazem têm de concordar.

| Constante do `*_map_pkg` | Constante do `config_pkg` |
| :--- | :--- |
| `IS_E` | `IS_E` |
| `HAS_<EXTENSÃO>`, `HAS_ICACHE`, `HAS_DCACHE`, `FLASH_ON_BUS`, `RAM_ON_BUS`, `BOOT_MEMORY_BITS`, `I_CACHE_WINDOW_BITS`, `D_CACHE_WINDOW_BITS` | A mesma |
| `FLASH_BASE_KIB`, `FLASH_END_KIB`, `RAM_BASE_KIB`, `RAM_END_KIB` | `FLASH_BASE`, `FLASH_END`, `RAM_BASE`, `RAM_END`, em bytes |

Só o pacote do mapa tem `BOOT_MEMORY_SIZE_BYTES`, as `*_STORAGE_BYTES`, `RAM_LAST_PAGE`, os tamanhos das caches, `PERIPH_COUNT`, `STRICT_PERIPH`, as tabelas `PERIPH_BASES` e `PERIPH_MASKS`, `<NOME>_BASE` e `<NOME>_INDEX` de cada periférico e as constantes do CLINT, do PLIC e do clock da SDRAM. Só o `config_pkg` tem a base e as larguras, os tipos, as compostas, as `HAS_` dos periféricos do núcleo e as funções. O pacote do mapa usa `addr_t` e `ADDR_BITS` do `config_pkg`, então o `config_pkg` vem antes dele na ordem de compilação. Um pacote do mapa não escreve um valor em KiB que não cabe num `natural`, nem a última página da RAM acima de 32 bits.

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
| `--set NOME=VALOR` | Troca `IS_64`, `IS_E` ou uma `HAS_*` (`true` ou `false`) ou `ADDR_BITS` (inteiro). Repetível |
| `--output` | Arquivo a escrever. Sem ele, o pacote vai para a saída padrão |

A variante é validada como uma plataforma própria, com V-A1 a V-A6 para o `ADDR_BITS` e o `IS_64` dela, e os periféricos da metade superior do espaço vão para a metade superior da nova largura, no mesmo slot de 1/16 do espaço e no mesmo deslocamento dentro dele. Um nome que não é constante do pacote é um erro, e uma variante com `HAS_ICACHE` ou `HAS_DCACHE` sobre uma memória que não está no barramento também. O cabeçalho do arquivo lista a variante.

### 10.5. Lista de fontes

O `sources` mantém um só `config_pkg.vhd` na lista. Quando o arquivo do Common-Components e o gerado da plataforma aparecem, fica o gerado, na posição do padrão, de modo que toda unidade que o usa vem depois dele (ver [sources](sources.md)).

### 10.6. Plataformas que precisam declarar mais

Algumas plataformas precisam de uma declaração a mais para que o `config_pkg` gerado reflita a escolha delas.

| Caso | O que declarar |
| :--- | :--- |
| Interrupções sem `Zicsr` no perfil padrão (a `check_isa` falha na elaboração) | Gerar a variante com `--set HAS_ZICSR=true`, ou ligar o `Zicsr` no perfil |
| Largura de endereço abaixo de 26 bits com caches | As janelas das caches nunca passam de `address_bits`, então a janela da tag é o espaço inteiro |

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
| `tests/test_groups.py` | Os blocos `gpio` e `seg_display`: o tamanho de 64 bytes por grupo para `solo`, `all`, `pairs`, `trios` e a lista explícita, os pinos desligados, `roles`, as regras G-0 a G-6 contra cada placa, o tamanho que não se escreve, o `RV32_<NOME>_G<k>_BASE` e o `rv32_platform.h` gerado. |
| `tests/test_layout.py` | O bloco `memory` vira as regiões e as quatro escolhas, dois segmentos são recusados ("vários segmentos ainda não são suportados"), as chaves antigas (`regions`, `memory.rom`, `kind`, `exec`) são recusadas com a migração, e `on_bus` vem nos dois segmentos ou em nenhum. O `tests/test_peripheral_offsets.py` prova que a ordem dos periféricos no arquivo é a ordem dos índices. |
| `tests/test_core_profile.py` | O bloco `core` e o perfil inferido (ordem da matriz, `Zicsr` junto de `Zicntr`, extras), `--profile` que mantém os extras, cada erro (extensão desconhecida ou repetida, combinação recusada, `type: 64` sem base `rv64`, `isa` no lugar de `base`), a recusa de `profile:` e `extras:` com a migração e o nome sem matriz. |
| `tests/test_peripheral_offsets.py` | A janela derivada do `size`, os símbolos `base`, `size`, `window` e `index`, uma rejeição para cada V-P1 a V-P5, a recusa de `id`, `offset` e `padding` com a mensagem de migração, as tabelas `PERIPH_BASES` e `PERIPH_MASKS`, a V-S1 e a `STRICT_PERIPH` no pacote do mapa. |
| `tests/test_address_bits.py` | O campo `address_bits`, uma rejeição para cada V-A1 a V-A6, a recusa de `periph_window` (V-P6), `resolve` com os perfis `rv64`, o `--profile` e as chaves novas do `config.yaml`. |
| `tests/test_config_pkg.py` | O `config_pkg` para 32, 24 e 40 bits, a base E, as variantes e o que elas recusam, as `HAS_` dos periféricos do núcleo, `FLASH_ON_BUS` e `RAM_ON_BUS`, a regra de cache (V-C1 e V-C2), a ordem do mapa do núcleo (V-M), a escrita com o mapa e o `--check`, a coerência entre os dois pacotes, o comando e a prova de que o pacote do mapa e o `config_pkg` do DE0-CV não mudam. |
| `tests/test_generate_memory_map.py` | Specs, linker script e pacote VHDL saem do mapa; `--check` pega arquivo ausente ou editado; endereço fora de KiB, janela de periférico sobre uma região e chave removida são rejeitados; o comando escreve e confere. |
| `tests/test_cxx_generate.py` | `cxx: true` troca o `*startfile`, acrescenta o `*endfile` e o `*self_spec`; sem ele o arquivo não muda; `syscalls` escreve as quatro funções e só vale com `cxx`. |
| `tests/test_interrupts.py` | O pacote traz `HAS_INTERRUPTS`, `CLOCK_HZ`, `MTIME_HZ` e `CLINT_TICK_CYCLES`, o cabeçalho traz os registradores do CLINT e a taxa do `mtime`, e uma seção inconsistente (taxa, CLINT ausente, perfil sem as interrupções) é rejeitada. |
| `tests/test_timers.py` | Zero, um, três e oito temporizadores dão as tabelas, as linhas e o cabeçalho, as fontes dos outros periféricos nunca mudam, o nome `TIMER` continua válido, e um tipo, tamanho, nome, alinhamento, sobreposição ou linha fixa errados é rejeitado. |
| `tests/test_memory_choice.py` | A seção `memory` e a opção `--memory` geram as 9 combinações válidas como 9 pacotes diferentes e recusam as 7 inválidas, as constantes e os parâmetros da simulação saem da escolha, e as regras V1 a V5, V7 e V10 falham com mensagem clara. |
| `tests/test_config_from_platform.py` | As chaves de `memory`, o ambiente do `tohost` e do `stdout` e as larguras de endereço saem do mapa, e o mapa vale mais que o arquivo e os seus `extends`. |

## 12. Uso

```bash
uv run riscv-tools --root <projeto> check-memory-map --platform platforms/internal-mem.yaml
```

Não precisa de `--config`. Status 1 e uma linha `MISMATCH` por divergência quando uma cópia diverge; feito para o CI.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
