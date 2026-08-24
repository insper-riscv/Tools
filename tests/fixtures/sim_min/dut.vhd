-- Minimal DUT for tests/test_sim_runner.py — NOT a real RV32 core,
-- just enough to prove sim_runner's cocotb/GHDL build+test+results
-- plumbing actually works end to end. Counts clock cycles since
-- reset and raises "mailbox" to 1 once it reaches CYCLES.
library ieee;
use ieee.std_logic_1164.all;

entity dut is
    generic (
        CYCLES : integer := 5
    );
    port (
        clk     : in  std_logic;
        rst     : in  std_logic;
        mailbox : out integer
    );
end entity dut;

architecture rtl of dut is
    signal counter : integer := 0;
begin
    process(clk, rst)
    begin
        if rst = '1' then
            counter <= 0;
        elsif rising_edge(clk) then
            if counter < CYCLES then
                counter <= counter + 1;
            end if;
        end if;
    end process;

    mailbox <= 1 when counter >= CYCLES else 0;
end architecture rtl;
