-- =====================================================================
-- Pacote de configuração da plataforma
-- =====================================================================
-- Constantes da plataforma, geradas por `riscv-tools` a partir de
-- src/cyclone-v/de0-cv/platform.yaml.
-- Não edite à mão: mude o YAML da plataforma e gere de novo.
--
-- A unidade tem o nome do pacote padrão do Common-Components, e esta
-- versão ocupa o lugar dele na lista de fontes. Os limites do mapa
-- estão em bytes, no tipo map_addr_t, e as funções isa_string e
-- check_isa descrevem e conferem a combinação de extensões.
-- =====================================================================

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package config_pkg is

	-- Base de 64 bits (RV64) quando verdadeiro, 32 bits (RV32) quando falso.
	constant IS_64              : boolean := false;
	-- Base E (16 registradores) quando verdadeiro, base I (32) quando falso.
	constant IS_BASE_E          : boolean := false;
	-- Largura do endereço físico em bits, de 16 a 64 (acima de 32 só com IS_64).
	constant ADDR_BITS          : natural := 32;
	-- Menor largura de endereço físico aceita.
	constant ADDR_BITS_MIN      : natural := 16;
	-- Maior largura de endereço físico aceita.
	constant ADDR_BITS_MAX      : natural := 64;
	-- Maior largura de endereço físico aceita sem IS_64.
	constant ADDR_BITS_MAX_RV32 : natural := 32;
	-- Largura da palavra de dados, do PC lógico e dos registradores.
	constant XLEN               : natural := 32;
	-- Número de registradores de uso geral.
	constant NUM_REGS           : natural := 32;
	-- Bits do índice de registrador.
	constant REG_BITS           : natural := 5;
	-- Palavra de dados de XLEN bits.
	subtype word_t is std_logic_vector((XLEN - 1) downto 0);
	-- Índice de registrador.
	subtype reg_t is std_logic_vector((REG_BITS - 1) downto 0);
	-- Endereço físico de ADDR_BITS bits.
	subtype addr_t is std_logic_vector((ADDR_BITS - 1) downto 0);
	-- Endereço de mapa com um bit a mais, para representar o fim exclusivo 2**ADDR_BITS.
	subtype map_addr_t is unsigned(ADDR_BITS downto 0);
	-- Tamanho do espaço de endereços, 2**ADDR_BITS bytes.
	constant ADDR_SPACE_BYTES   : map_addr_t := shift_left(to_unsigned(1, map_addr_t'length), ADDR_BITS);

	-- Presença de M na plataforma.
	constant HAS_M              : boolean := true;
	-- Presença de Zmmul na plataforma.
	constant HAS_ZMMUL          : boolean := false;
	-- Presença de Zicsr na plataforma.
	constant HAS_ZICSR          : boolean := true;
	-- Presença de Zicntr na plataforma.
	constant HAS_ZICNTR         : boolean := true;
	-- Presença de Zihpm na plataforma.
	constant HAS_ZIHPM          : boolean := true;
	-- Presença de Zimop na plataforma.
	constant HAS_ZIMOP          : boolean := true;
	-- Presença de Zicond na plataforma.
	constant HAS_ZICOND         : boolean := true;
	-- Presença de Zihintntl na plataforma.
	constant HAS_ZIHINTNTL      : boolean := true;
	-- Presença de Zihintpause na plataforma.
	constant HAS_ZIHINTPAUSE    : boolean := true;
	-- Presença de Zifencei na plataforma.
	constant HAS_ZIFENCEI       : boolean := true;
	-- Presença de Zicclsm na plataforma.
	constant HAS_ZICCLSM        : boolean := true;
	-- Presença de Interrupts na plataforma.
	constant HAS_INTERRUPTS     : boolean := true;
	-- Presença de Sscofpmf na plataforma.
	constant HAS_SSCOFPMF       : boolean := true;
	-- Presença de Access faults na plataforma.
	constant HAS_ACCESS_FAULTS  : boolean := true;
	-- Presença de Icache na plataforma.
	constant HAS_ICACHE         : boolean := true;
	-- Presença de Dcache na plataforma.
	constant HAS_DCACHE         : boolean := true;

	-- Há multiplicação de inteiros, com M ou com Zmmul.
	constant HAS_MULDIV         : boolean := HAS_M or HAS_ZMMUL;
	-- Há contadores de desempenho, com Zicntr ou com Zihpm.
	constant HAS_ANY_COUNTER    : boolean := HAS_ZICNTR or HAS_ZIHPM;
	-- O estouro de contador gera interrupção: Sscofpmf com Zihpm e interrupções.
	constant HAS_SSCOF          : boolean := HAS_SSCOFPMF and HAS_ZIHPM and HAS_INTERRUPTS;

	-- A ROM fica fora do núcleo.
	constant ROM_EXTERNAL       : boolean := true;
	-- A RAM fica fora do núcleo.
	constant RAM_EXTERNAL       : boolean := true;
	-- Expoente do tamanho da BOOT_MEMORY, em bytes (2**BOOT_MEMORY_BITS).
	constant BOOT_MEMORY_BITS   : natural := 12;
	-- Largura da janela de endereços das caches, em bits: a tag guarda os bits abaixo dela.
	constant CACHE_WINDOW_BITS  : natural := 26;

	-- Base da ROM, em bytes.
	constant ROM_BASE           : map_addr_t := resize(unsigned'(x"000001000"), map_addr_t'length);
	-- Fim exclusivo da ROM, em bytes.
	constant ROM_END            : map_addr_t := resize(unsigned'(x"000040000"), map_addr_t'length);
	-- Base da RAM, em bytes.
	constant RAM_BASE           : map_addr_t := resize(unsigned'(x"040000000"), map_addr_t'length);
	-- Fim exclusivo da RAM, em bytes.
	constant RAM_END            : map_addr_t := resize(unsigned'(x"044000000"), map_addr_t'length);
	-- Base da janela externa, em bytes.
	constant EXT_BASE           : map_addr_t := resize(unsigned'(x"080000000"), map_addr_t'length);
	-- Base da janela de periféricos, em bytes.
	constant PERIPH_BASE        : map_addr_t := resize(unsigned'(x"080000000"), map_addr_t'length);

	-- Janelas de periférico que têm periférico (bit n para o índice n).
	subtype periph_slots_t is std_logic_vector(7 downto 0);
	-- Janelas de periférico ocupadas na plataforma.
	constant PERIPH_SLOTS       : periph_slots_t := "11111000";
	-- O periférico UART está presente na plataforma.
	constant HAS_UART           : boolean := true;
	-- O periférico UART_PINS está presente na plataforma.
	constant HAS_UART_PINS      : boolean := false;
	-- O periférico UART_JTAG está presente na plataforma.
	constant HAS_UART_JTAG      : boolean := true;
	-- O periférico TIMER está presente na plataforma.
	constant HAS_TIMER          : boolean := false;
	-- O periférico GPIO está presente na plataforma.
	constant HAS_GPIO           : boolean := false;
	-- O periférico DISPLAY está presente na plataforma.
	constant HAS_DISPLAY        : boolean := true;
	-- O periférico SWITCHES está presente na plataforma.
	constant HAS_SWITCHES       : boolean := false;
	-- O periférico KEYS está presente na plataforma.
	constant HAS_KEYS           : boolean := false;
	-- O periférico CLINT está presente na plataforma.
	constant HAS_CLINT          : boolean := true;
	-- O periférico PLIC está presente na plataforma.
	constant HAS_PLIC           : boolean := true;
	-- O periférico FLASH_CTRL está presente na plataforma.
	constant HAS_FLASH_CTRL     : boolean := true;

	-- Texto da ISA da configuração, como rv32im_zicsr.
	function isa_string return string;
	-- Confere as dependências entre as constantes; falha na elaboração
	-- se a combinação é inválida e devolve verdadeiro se é válida.
	function check_isa return boolean;

end package config_pkg;

package body config_pkg is

	function isa_string return string is
		-- Tamanho do espaço para montar o texto da ISA.
		constant ISA_STRING_MAX : natural := 160;
		-- Texto montado, preenchido a partir da primeira posição.
		variable text : string(1 to ISA_STRING_MAX) := (others => ' ');
		-- Quantidade de caracteres já escritos em text.
		variable used : natural := 0;
		-- Acrescenta um trecho ao fim do texto.
		procedure add (piece : string) is
		begin
			for index in piece'range loop
				used := used + 1;
				text(used) := piece(index);
			end loop;
		end procedure add;
	begin
		if IS_64 then
			add("rv64");
		else
			add("rv32");
		end if;
		if IS_BASE_E then
			add("e");
		else
			add("i");
		end if;
		if HAS_M then
			add("m");
		end if;
		if HAS_ZICCLSM then
			add("_zicclsm");
		end if;
		if HAS_ZICNTR then
			add("_zicntr");
		end if;
		if HAS_ZICOND then
			add("_zicond");
		end if;
		if HAS_ZICSR then
			add("_zicsr");
		end if;
		if HAS_ZIFENCEI then
			add("_zifencei");
		end if;
		if HAS_ZIHINTNTL then
			add("_zihintntl");
		end if;
		if HAS_ZIHINTPAUSE then
			add("_zihintpause");
		end if;
		if HAS_ZIHPM then
			add("_zihpm");
		end if;
		if HAS_ZIMOP then
			add("_zimop");
		end if;
		if HAS_ZMMUL then
			add("_zmmul");
		end if;
		if HAS_SSCOFPMF then
			add("_sscofpmf");
		end if;
		return text(1 to used);
	end function isa_string;

	function check_isa return boolean is
	begin
		assert ADDR_BITS >= ADDR_BITS_MIN and ADDR_BITS <= ADDR_BITS_MAX
			report "ADDR_BITS fora da faixa de 16 a 64"
			severity failure;
		assert IS_64 or ADDR_BITS <= ADDR_BITS_MAX_RV32
			report "ADDR_BITS acima de 32 exige IS_64"
			severity failure;
		assert HAS_ZICSR or not HAS_ANY_COUNTER
			report "Zicntr e Zihpm exigem Zicsr"
			severity failure;
		assert HAS_ZICSR or not HAS_INTERRUPTS
			report "Interrupts exige Zicsr"
			severity failure;
		assert HAS_ZICSR or not HAS_ACCESS_FAULTS
			report "AccessFaults exige Zicsr"
			severity failure;
		assert HAS_SSCOF or not HAS_SSCOFPMF
			report "Sscofpmf exige Zihpm e Interrupts"
			severity failure;
		assert ROM_BASE < ROM_END
			report "ROM_BASE deve ser menor que ROM_END"
			severity failure;
		assert RAM_BASE < RAM_END
			report "RAM_BASE deve ser menor que RAM_END"
			severity failure;
		assert ROM_END <= RAM_BASE or RAM_END <= ROM_BASE
			report "A ROM e a RAM se sobrepoem"
			severity failure;
		assert ROM_END <= ADDR_SPACE_BYTES and RAM_END <= ADDR_SPACE_BYTES
			report "A ROM ou a RAM passa de 2**ADDR_BITS bytes"
			severity failure;
		assert ROM_END <= PERIPH_BASE and RAM_END <= PERIPH_BASE
			report "A ROM ou a RAM passa da janela de perifericos"
			severity failure;
		return true;
	end function check_isa;

end package body config_pkg;
