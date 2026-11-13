-- ===========================================================================
-- Mapa de memória da plataforma, gerado por
-- `riscv-tools generate-memory-map` a partir de src/cyclone-v/de0-cv/platform.yaml.
--
-- Não edite à mão: mude o YAML da plataforma e rode o comando de novo. Os
-- limites estão em KiB, como os genéricos do núcleo, e os endereços dos
-- periféricos em bytes.
-- ===========================================================================

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.config_pkg.ADDR_BITS;
use work.config_pkg.addr_t;

package de0_cv_map_pkg is

	-- O perfil é o RV32E (16 registradores); falso é o RV32I (32).
	constant IS_E                : boolean  := false;
	-- A extensão M está no perfil.
	constant HAS_M               : boolean  := true;
	-- A extensão Zmmul está no perfil.
	constant HAS_ZMMUL           : boolean  := false;
	-- A extensão Zicsr está no perfil.
	constant HAS_ZICSR           : boolean  := true;
	-- A extensão Zicntr está no perfil.
	constant HAS_ZICNTR          : boolean  := true;
	-- A extensão Zihpm está no perfil.
	constant HAS_ZIHPM           : boolean  := true;
	-- A extensão Zimop está no perfil.
	constant HAS_ZIMOP           : boolean  := true;
	-- A extensão Zicond está no perfil.
	constant HAS_ZICOND          : boolean  := true;
	-- A extensão Zihintntl está no perfil.
	constant HAS_ZIHINTNTL       : boolean  := true;
	-- A extensão Zihintpause está no perfil.
	constant HAS_ZIHINTPAUSE     : boolean  := true;
	-- A extensão Zifencei está no perfil.
	constant HAS_ZIFENCEI        : boolean  := true;
	-- A extensão Zicclsm está no perfil.
	constant HAS_ZICCLSM         : boolean  := true;
	-- A extensão Interrupts está no perfil.
	constant HAS_INTERRUPTS      : boolean  := true;
	-- A extensão Sscofpmf está no perfil.
	constant HAS_SSCOFPMF        : boolean  := true;
	-- A extensão Access_faults está no perfil.
	constant HAS_ACCESS_FAULTS   : boolean  := true;
	-- Expoente do tamanho da BOOT_MEMORY, em [0, 2**BOOT_MEMORY_BITS).
	constant BOOT_MEMORY_BITS       : natural  := 12;
	-- Tamanho da BOOT_MEMORY, em bytes.
	constant BOOT_MEMORY_SIZE_BYTES : positive := 4096;
	-- Base da FLASH, em KiB, logo depois da BOOT_MEMORY.
	constant FLASH_BASE_KIB      : natural  := 4;
	-- Fim exclusivo da FLASH, em KiB.
	constant FLASH_END_KIB       : natural  := 256;
	-- Armazenamento da FLASH, em bytes: a menor potência de dois que cobre
	-- [0, fim da FLASH).
	constant FLASH_STORAGE_BYTES : positive := 262144;
	-- A FLASH é alcançada pelo barramento (verdadeiro) ou pela porta direta (falso).
	constant FLASH_ON_BUS        : boolean  := true;
	-- Base da RAM, em KiB.
	constant RAM_BASE_KIB        : natural  := 1048576;
	-- Fim exclusivo da RAM, em KiB.
	constant RAM_END_KIB         : natural  := 1114112;
	-- Armazenamento da RAM, em bytes: a menor potência de dois que cobre
	-- o tamanho da RAM.
	constant RAM_STORAGE_BYTES   : positive := 67108864;
	-- Página de 4 KiB no topo da RAM (bits 31:12 do endereço), onde ficam as
	-- palavras que o hospedeiro compartilha com o programa.
	constant RAM_LAST_PAGE       : std_logic_vector(19 downto 0) :=
		x"43FFF";
	-- A RAM é alcançada pelo barramento (verdadeiro) ou pela porta direta (falso).
	constant RAM_ON_BUS          : boolean  := true;
	-- Existe cache de instruções.
	constant HAS_ICACHE          : boolean  := true;
	-- Existe cache de dados.
	constant HAS_DCACHE          : boolean  := true;
	-- Tamanho da cache de instruções, em bits (256 se não existe).
	constant ICACHE_SIZE_BITS    : positive := 32768;
	-- Tamanho da cache de dados, em bits (256 se não existe).
	constant DCACHE_SIZE_BITS    : positive := 32768;
	-- Largura da janela de endereços da cache de instruções, em bits: a tag guarda os bits abaixo dela (26 é 64 MiB, 27 é 128 MiB).
	constant I_CACHE_WINDOW_BITS : natural  := 26;
	-- Largura da janela de endereços da cache de dados, em bits: a tag guarda os bits abaixo dela (26 é 64 MiB, 27 é 128 MiB).
	constant D_CACHE_WINDOW_BITS : natural  := 26;

	-- Número de periféricos do mapa, o tamanho das tabelas abaixo.
	constant PERIPH_COUNT : natural := 5;
	-- Periféricos estritos: o interconector termina com erro o acesso ao que sobra da janela depois dos registradores.
	constant STRICT_PERIPH : boolean := true;
	-- Tabela de endereços, um por periférico.
	type periph_addr_array_t is array (natural range <>) of addr_t;

	-- Endereço base do periférico FLASH_CTRL.
	constant FLASH_CTRL_BASE : addr_t := std_logic_vector(resize(unsigned'(x"B0000000"), ADDR_BITS));
	-- Índice do periférico FLASH_CTRL nas tabelas PERIPH_BASES e PERIPH_MASKS.
	constant FLASH_CTRL_INDEX : natural := 0;

	-- Endereço base do periférico UART.
	constant UART_BASE : addr_t := std_logic_vector(resize(unsigned'(x"C0000000"), ADDR_BITS));
	-- Índice do periférico UART nas tabelas PERIPH_BASES e PERIPH_MASKS.
	constant UART_INDEX : natural := 1;

	-- Endereço base do periférico DISPLAY.
	constant DISPLAY_BASE : addr_t := std_logic_vector(resize(unsigned'(x"D0000000"), ADDR_BITS));
	-- Índice do periférico DISPLAY nas tabelas PERIPH_BASES e PERIPH_MASKS.
	constant DISPLAY_INDEX : natural := 2;

	-- Endereço base do periférico CLINT.
	constant CLINT_BASE : addr_t := std_logic_vector(resize(unsigned'(x"E0000000"), ADDR_BITS));
	-- Índice do periférico CLINT nas tabelas PERIPH_BASES e PERIPH_MASKS.
	constant CLINT_INDEX : natural := 3;

	-- Endereço base do periférico PLIC.
	constant PLIC_BASE : addr_t := std_logic_vector(resize(unsigned'(x"F0000000"), ADDR_BITS));
	-- Índice do periférico PLIC nas tabelas PERIPH_BASES e PERIPH_MASKS.
	constant PLIC_INDEX : natural := 4;

	-- Base de cada periférico, na ordem de `peripherals`.
	constant PERIPH_BASES : periph_addr_array_t(0 to PERIPH_COUNT - 1) := (
		FLASH_CTRL_INDEX => FLASH_CTRL_BASE,
		UART_INDEX => UART_BASE,
		DISPLAY_INDEX => DISPLAY_BASE,
		CLINT_INDEX => CLINT_BASE,
		PLIC_INDEX => PLIC_BASE
	);

	-- Máscara de cada janela: o periférico i responde quando (endereço and PERIPH_MASKS(i)) = PERIPH_BASES(i); a janela é a menor potência de dois que cobre o tamanho, com no mínimo 16 bytes.
	constant PERIPH_MASKS : periph_addr_array_t(0 to PERIPH_COUNT - 1) := (
		FLASH_CTRL_INDEX => std_logic_vector(resize(unsigned'(x"FFFFFFC0"), ADDR_BITS)),
		UART_INDEX => std_logic_vector(resize(unsigned'(x"FFFFFFF0"), ADDR_BITS)),
		DISPLAY_INDEX => std_logic_vector(resize(unsigned'(x"FFFFFFF0"), ADDR_BITS)),
		CLINT_INDEX => std_logic_vector(resize(unsigned'(x"FFFF0000"), ADDR_BITS)),
		PLIC_INDEX => std_logic_vector(resize(unsigned'(x"FFC00000"), ADDR_BITS))
	);

	-- Frequência do clock do domínio do núcleo e do CLINT, em Hz.
	constant CLOCK_HZ          : positive := 77000000;
	-- Frequência com que o mtime do CLINT conta, em Hz; é independente do CSR time.
	constant MTIME_HZ          : positive := 1000000;
	-- Ciclos de clock por incremento do mtime (tick_cycles do CLINT).
	constant CLINT_TICK_CYCLES : positive := 77;

	-- Número de fontes do PLIC (o maior identificador de fonte).
	constant PLIC_N_SOURCES     : positive := 6;
	-- Largura da prioridade e do limiar do PLIC, em bits.
	constant PLIC_PRIORITY_BITS : positive := 3;
	-- Largura do endereço de palavra da janela do PLIC.
	constant PLIC_ADDR_WIDTH    : positive := 20;
	-- Identificador da fonte UART_JTAG no PLIC.
	constant IRQ_UART_JTAG : positive := 2;
	-- Identificador da fonte FLASH no PLIC.
	constant IRQ_FLASH : positive := 6;

	-- Número de temporizadores de uso geral do mapa (`kind: timer`), o tamanho das tabelas abaixo.
	constant TIMER_COUNT : natural := 0;
	-- Índice de cada temporizador nas tabelas PERIPH_BASES e PERIPH_MASKS, na ordem de `peripherals`.
	constant TIMER_INDICES : integer_vector(0 to TIMER_COUNT - 1) := (
		others => 0
	);
	-- Fonte do PLIC de cada temporizador, na mesma ordem (zero sem PLIC).
	constant TIMER_IRQ_IDS : integer_vector(0 to TIMER_COUNT - 1) := (
		others => 0
	);

	-- Frequência do clock do controlador da SDRAM, em Hz.
	constant SDRAM_CLOCK_HZ : positive := 100000000;
	-- Período desse clock, em picossegundos: a base da conversão dos tempos do chip em ciclos.
	constant SDRAM_TCK_PS   : positive := 10000;

end package de0_cv_map_pkg;
