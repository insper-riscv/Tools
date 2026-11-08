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

package de0_cv_map_pkg is

	-- O perfil é o RV32E (16 registradores); falso é o RV32I (32).
	constant HAS_E               : boolean  := false;
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
	-- Base da ROM, em KiB, logo depois da BOOT_MEMORY.
	constant ROM_BASE_KIB        : natural  := 4;
	-- Fim exclusivo da ROM, em KiB.
	constant ROM_END_KIB         : natural  := 256;
	-- Armazenamento da ROM, em bytes: a menor potência de dois que cobre
	-- [0, fim da ROM).
	constant ROM_STORAGE_BYTES   : positive := 262144;
	-- A ROM fica fora do núcleo.
	constant ROM_EXTERNAL        : boolean  := true;
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
	-- A RAM fica fora do núcleo.
	constant RAM_EXTERNAL        : boolean  := true;
	-- Base da janela externa, em KiB; dali em diante é externo.
	constant EXT_BASE_KIB        : natural  := 2097152;
	-- Base da janela de periféricos, em KiB: os 2 GiB superiores do espaço.
	constant PERIPH_BASE_KIB     : natural  := 2097152;
	-- Existe cache de instruções.
	constant HAS_ICACHE          : boolean  := true;
	-- Existe cache de dados.
	constant HAS_DCACHE          : boolean  := true;
	-- Tamanho da cache de instruções, em bits (256 se não existe).
	constant ICACHE_SIZE_BITS    : positive := 32768;
	-- Tamanho da cache de dados, em bits (256 se não existe).
	constant DCACHE_SIZE_BITS    : positive := 32768;
	-- Largura da janela de endereços das caches, em bits: a tag guarda os bits abaixo dela (26 é 64 MiB, 27 é 128 MiB).
	constant CACHE_WINDOW_BITS   : natural  := 26;
	-- A ROM é alcançada pela porta do núcleo (externa ou com cache).
	constant ROM_VIA_PORT        : boolean  := ROM_EXTERNAL or HAS_ICACHE;
	-- A RAM é alcançada pela porta do núcleo (externa ou com cache).
	constant RAM_VIA_PORT        : boolean  := RAM_EXTERNAL or HAS_DCACHE;

	-- Janelas de 256 MiB do barramento de periféricos que têm periférico (bit n para o índice n, bits 30:28 do endereço).
	constant PERIPH_SLOTS : std_logic_vector(7 downto 0) := "11111000";

	-- Endereço base do periférico FLASH_CTRL.
	constant FLASH_CTRL_BASE : std_logic_vector(31 downto 0) := x"B0000000";
	-- Índice da janela de 256 MiB do periférico FLASH_CTRL (bits 30:28 do endereço).
	constant FLASH_CTRL_ID   : natural := 3;

	-- Endereço base do periférico UART.
	constant UART_BASE : std_logic_vector(31 downto 0) := x"C0000000";
	-- Índice da janela de 256 MiB do periférico UART (bits 30:28 do endereço).
	constant UART_ID   : natural := 4;

	-- Endereço base do periférico DISPLAY.
	constant DISPLAY_BASE : std_logic_vector(31 downto 0) := x"D0000000";
	-- Índice da janela de 256 MiB do periférico DISPLAY (bits 30:28 do endereço).
	constant DISPLAY_ID   : natural := 5;

	-- Endereço base do periférico CLINT.
	constant CLINT_BASE : std_logic_vector(31 downto 0) := x"E0000000";
	-- Índice da janela de 256 MiB do periférico CLINT (bits 30:28 do endereço).
	constant CLINT_ID   : natural := 6;

	-- Endereço base do periférico PLIC.
	constant PLIC_BASE : std_logic_vector(31 downto 0) := x"F0000000";
	-- Índice da janela de 256 MiB do periférico PLIC (bits 30:28 do endereço).
	constant PLIC_ID   : natural := 7;

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

	-- Frequência do clock do controlador da SDRAM, em Hz.
	constant SDRAM_CLOCK_HZ : positive := 100000000;
	-- Período desse clock, em picossegundos: a base da conversão dos tempos do chip em ciclos.
	constant SDRAM_TCK_PS   : positive := 10000;

end package de0_cv_map_pkg;
