-- Library "helper" for tests/test_sim_runner.py: analyzed on its own by
-- sim_runner.build_libraries, the way a vendor simulation library such
-- as altera_mf is. It uses ieee.std_logic_unsigned, which GHDL only
-- accepts with -fsynopsys, so the test also proves sim.ghdl_flags
-- reaches the analyze step.
library ieee;
use ieee.std_logic_1164.all;
use ieee.std_logic_unsigned.all;

package helper_pkg is
    function bump (v : std_logic_vector(7 downto 0)) return std_logic_vector;
end package helper_pkg;

package body helper_pkg is
    function bump (v : std_logic_vector(7 downto 0)) return std_logic_vector is
    begin
        return v + 1;
    end function bump;
end package body helper_pkg;
