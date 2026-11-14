-- =============================================================================
-- Pacote de configuração da plataforma (constantes de elaboração)
--
-- Espelho único, em VHDL, do que o platform.yaml escolhe: a base da ISA
-- (IS_64, IS_E), a largura do endereço físico (ADDR_BITS), os tipos
-- derivados (word_t, reg_t, addr_t, map_addr_t), uma constante HAS_* por
-- extensão, cache e periférico que interage com o núcleo, e o mapa de
-- memória em bytes. Todo módulo lê estas constantes e usa generate sobre
-- elas; extensão desligada não gera lógica.
--
-- Este arquivo traz os valores padrão (RV32I_Zicclsm, endereço de 32 bits, sem
-- periféricos), que os testes dos módulos usam. O topo de uma plataforma e
-- as provas formais trocam este arquivo, na lista de fontes, por uma versão
-- gerada com o mesmo nome de unidade e as mesmas constantes. O pacote é de
-- constantes e não genérico porque o Quartus Prime Lite recusa pacote
-- genérico.
--
-- A função check_isa confere as dependências entre as constantes e falha na
-- elaboração (severity failure) quando a configuração é inválida. Ela é
-- chamada uma vez, no generate da entidade de topo da cadeia (if check_isa
-- generate), e não em constante deste pacote. A função isa_string devolve o
-- nome da ISA configurada, como rv32i_zicclsm, para o relatório da elaboração.
-- =============================================================================

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.utils_pkg.all;

package config_pkg is

    -- Configuração base do processador

    -- Base de 64 bits (RV64) quando verdadeiro, de 32 bits (RV32) quando falso.
    constant IS_64     : boolean := false;
    -- Base E (16 registradores) quando verdadeiro, base I (32) quando falso.
    constant IS_E : boolean := false;
    -- Largura do endereço físico em bits, de 16 a XLEN (o núcleo não tem MMU, então o endereço efetivo nunca passa de XLEN bits).
    constant ADDR_BITS : natural := 32;

    -- Constantes auxiliares derivadas da configuração base

    -- Largura em bits da palavra de dados, do PC lógico e dos registradores.
    constant XLEN     : natural := pick(IS_64, 64, 32);
    -- Largura em bits do índice de registrador: 4 na base E e 5 na base I.
    constant REG_BITS : natural := pick(IS_E, 4, 5);
    -- Número de registradores de uso geral, 2 elevado a REG_BITS.
    constant NUM_REGS : natural := 2 ** REG_BITS;

    -- Definições de tipos derivados da configuração base

    -- Palavra de dados de XLEN bits.
    subtype word_t is std_logic_vector((XLEN - 1) downto 0);

    -- Índice de registrador de uso geral de REG_BITS bits.
    subtype reg_t is std_logic_vector((REG_BITS - 1) downto 0);

    -- Endereço físico de ADDR_BITS bits.
    subtype addr_t is std_logic_vector((ADDR_BITS - 1) downto 0);

    -- Endereço de mapa em bytes, com um bit a mais para representar o fim exclusivo 2**ADDR_BITS.
    subtype map_addr_t is unsigned(ADDR_BITS downto 0);

    -- Ajuste do sistema de memória

    -- Existe cache de instruções; exige FLASH_ON_BUS.
    constant HAS_ICACHE   : boolean := false;
    -- A FLASH é alcançada pelo barramento (verdadeiro) ou pela porta direta do núcleo (falso).
    constant FLASH_ON_BUS : boolean := false;
    -- A RAM é alcançada pelo barramento (verdadeiro) ou pela porta direta do núcleo (falso).
    constant RAM_ON_BUS   : boolean := false;
    -- Existe cache de dados; exige RAM_ON_BUS.
    constant HAS_DCACHE   : boolean := false;

    -- Extensões de memória

    -- Acesso desalinhado à memória principal atendido em hardware (Zicclsm).
    constant HAS_ZICCLSM  : boolean := true;
    -- Extensão Zifencei (fence.i) presente.
    constant HAS_ZIFENCEI : boolean := false;

    -- Extensões do conjunto de instruções I

    -- Extensão Zimop (mop.r.n e mop.rr.n) presente.
    constant HAS_ZIMOP         : boolean := false;
    -- Extensão Zicond (czero.eqz e czero.nez) presente.
    constant HAS_ZICOND        : boolean := false;

    -- Extensões MISA

    -- Extensão Zmmul (só multiplicação) presente.
    constant HAS_ZMMUL         : boolean := false;
    -- Extensão M (multiplicação e divisão) presente; se true, Zmmul é ignorada.
    constant HAS_M             : boolean := false;

    -- Extensões de controle e status

    -- Extensão Zicsr e tratamento de exceções do modo máquina presentes.
    constant HAS_ZICSR         : boolean := false;
    -- Interrupções de máquina presentes (mip e mie); exige HAS_ZICSR.
    constant HAS_INTERRUPTS    : boolean := false;
    -- Falhas de acesso (causas 1, 5 e 7) geradas fora do mapa válido; exige HAS_ZICSR.
    constant HAS_ACCESS_FAULTS : boolean := false;
    -- Extensão Zicntr (mcycle, minstret, time) presente; exige HAS_ZICSR.
    constant HAS_ZICNTR        : boolean := false;
    -- Extensão Zihpm (contadores de eventos) presente; exige HAS_ZICSR.
    constant HAS_ZIHPM         : boolean := false;
    -- Extensão Sscofpmf (estouro de contador de eventos) presente; exige HAS_ZIHPM e HAS_INTERRUPTS.
    constant HAS_SSCOFPMF      : boolean := false;

    -- Extensões Hint

    -- Extensão Zihintntl (dicas ntl.*) presente.
    constant HAS_ZIHINTNTL     : boolean := false;
    -- Extensão Zihintpause (dica pause) presente.
    constant HAS_ZIHINTPAUSE   : boolean := false;

    -- Constantes derivadas de dependências entre extensões

    -- Multiplicação presente, por M ou por Zmmul.
    constant HAS_MULTIPLICATION : boolean := HAS_M or HAS_ZMMUL;
    -- Algum contador de hardware presente, Zicntr ou Zihpm.
    constant HAS_ANY_COUNTER    : boolean := HAS_ZICNTR or HAS_ZIHPM;
    -- Interrupção de estouro de contador (Sscofpmf) ativa, o que exige Zihpm e interrupções.
    constant HAS_SSCOF          : boolean := HAS_SSCOFPMF and HAS_ZIHPM and HAS_INTERRUPTS;

    -- Configurações das memórias principais (BOOT, $I, FLASH, $D e RAM).

    -- Configurações da BOOT_MEMORY (memória de inicialização).

    -- Expoente do tamanho da BOOT_MEMORY, que ocupa os endereços [0, 2**BOOT_MEMORY_BITS).
    constant BOOT_MEMORY_BITS  : natural    := 12;
    -- Base da BOOT_MEMORY em bytes, sempre o endereço 0.
    constant BOOT_MEMORY_BASE  : map_addr_t := to_unsigned(0, ADDR_BITS + 1);
    -- Fim exclusivo da BOOT_MEMORY em bytes, 2**BOOT_MEMORY_BITS.
    constant BOOT_MEMORY_END   : map_addr_t := shift_left(to_unsigned(1, ADDR_BITS + 1), BOOT_MEMORY_BITS);

    -- Configurações da FLASH (memória de instruções)

    -- Largura em bits da janela de endereços da cache de instruções, se cache estiver habilitada (12 = 4 KiB).
    constant I_CACHE_WINDOW_BITS : natural    := 12;
    -- Base da FLASH em bytes, logo depois da BOOT_MEMORY.
    constant FLASH_BASE          : map_addr_t := resize(unsigned'(x"00001000"), ADDR_BITS + 1);
    -- Fim exclusivo da FLASH em bytes.
    constant FLASH_END           : map_addr_t := resize(unsigned'(x"00008000"), ADDR_BITS + 1);

    -- Configurações da RAM (memória de dados)

    -- Largura em bits da janela de endereços da cache de dados, se cache estiver habilitada (12 = 4 KiB).
    constant D_CACHE_WINDOW_BITS : natural    := 12;
    -- Base da RAM em bytes.
    constant RAM_BASE            : map_addr_t := resize(unsigned'(x"00008000"), ADDR_BITS + 1);
    -- Fim exclusivo da RAM em bytes.
    constant RAM_END             : map_addr_t := resize(unsigned'(x"40000000"), ADDR_BITS + 1);

    -- Devolve o nome da ISA configurada, como rv32im_zicclsm, na ordem canônica das extensões.
    function isa_string return string;

    -- Confere as dependências entre as constantes e falha na elaboração quando a configuração é
    -- inválida; devolve sempre verdadeiro.

    function check_isa return boolean;

end package config_pkg;

package body config_pkg is

    function isa_string return string is

        -- Texto acumulado, com folga para todas as extensões.
        variable text  : string(1 to 128) := (others => ' ');
        -- Número de caracteres já escritos em text.
        variable count : natural          := 0;

        -- Acrescenta o trecho s ao final do texto.

        procedure add (
            s : in string
        ) is
        begin

            for i in s'range loop

                count       := count + 1;
                text(count) := s(i);

            end loop;

        end procedure add;

        -- Acrescenta o trecho s quando a condição cond é verdadeira.

        procedure add_if (
            cond : in boolean;
            s    : in string
        ) is
        begin

            if cond then
                add(s);
            end if;

        end procedure add_if;

    begin

        add_if(IS_64, "rv64");
        add_if(not IS_64, "rv32");
        add_if(IS_E, "e");
        add_if(not IS_E, "i");
        add_if(HAS_M, "m");
        add_if(HAS_ZICCLSM, "_zicclsm");
        add_if(HAS_ZICNTR, "_zicntr");
        add_if(HAS_ZICOND, "_zicond");
        add_if(HAS_ZICSR, "_zicsr");
        add_if(HAS_ZIFENCEI, "_zifencei");
        add_if(HAS_ZIHINTNTL, "_zihintntl");
        add_if(HAS_ZIHINTPAUSE, "_zihintpause");
        add_if(HAS_ZIHPM, "_zihpm");
        add_if(HAS_ZIMOP, "_zimop");
        add_if(HAS_ZMMUL and not HAS_M, "_zmmul");
        add_if(HAS_SSCOFPMF, "_sscofpmf");
        return text(1 to count);

    end function isa_string;

    function check_isa return boolean is

        -- Um, na largura de map_addr_t, base das potências de dois do mapa.
        constant ONE       : map_addr_t := to_unsigned(1, ADDR_BITS + 1);
        -- Fim do espaço de endereços físico em bytes, 2**ADDR_BITS.
        constant SPACE_END : map_addr_t := shift_left(ONE, ADDR_BITS);

    begin

        assert not (HAS_ZICNTR or HAS_ZIHPM) or HAS_ZICSR
            report "Zicntr e Zihpm exigem Zicsr"
            severity failure;
        assert not HAS_INTERRUPTS or HAS_ZICSR
            report "Interrupcoes exigem Zicsr"
            severity failure;
        assert not HAS_SSCOFPMF or (HAS_ZIHPM and HAS_INTERRUPTS)
            report "Sscofpmf exige Zihpm e interrupcoes"
            severity failure;
        assert not HAS_ACCESS_FAULTS or HAS_ZICSR
            report "Falhas de acesso exigem Zicsr"
            severity failure;
        assert ADDR_BITS >= 16 and ADDR_BITS <= 64
            report "ADDR_BITS fora de 16..64"
            severity failure;
        assert ADDR_BITS <= XLEN
            report "ADDR_BITS maior que XLEN"
            severity failure;
        assert BOOT_MEMORY_BITS < ADDR_BITS
            report "BOOT_MEMORY_BITS deve ser menor que ADDR_BITS"
            severity failure;
        assert BOOT_MEMORY_BASE = 0
            report "A BOOT_MEMORY deve comecar no endereco 0"
            severity failure;
        assert BOOT_MEMORY_END <= FLASH_BASE
            report "A memoria de instruções deve comecar depois da BOOT_MEMORY"
            severity failure;
        assert FLASH_BASE < FLASH_END
            report "A FLASH deve ter tamanho positivo"
            severity failure;
        assert FLASH_END <= RAM_BASE
            report "A memoria de instruções deve terminar antes da RAM"
            severity failure;
        assert RAM_BASE < RAM_END
            report "A RAM deve ter tamanho positivo"
            severity failure;
        assert RAM_END <= SPACE_END
            report "A RAM deve caber no espaço de endereços fisico"
            severity failure;
        assert not HAS_ICACHE or FLASH_ON_BUS
            report "Cache de instruções exige FLASH_ON_BUS"
            severity failure;
        assert not HAS_DCACHE or RAM_ON_BUS
            report "Cache de dados exige RAM_ON_BUS"
            severity failure;
        return true;

    end function check_isa;

end package body config_pkg;
