-- DUT for tests/test_sim_runner.py's library/run-file test. Reads an
-- integer from "data.txt" in the simulator's working directory (the way
-- an altsyncram init_file is read), and publishes it plus one through
-- helper_pkg.bump, a function from the separately analyzed library
-- "helper".
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;

library helper;
use helper.helper_pkg.all;

entity dut is
    port (
        clk     : in  std_logic;
        mailbox : out integer
    );
end entity dut;

architecture rtl of dut is
    impure function read_value return integer is
        file data_file : text open read_mode is "data.txt";
        variable row   : line;
        variable value : integer;
    begin
        readline(data_file, row);
        read(row, value);
        return value;
    end function read_value;

    constant BASE : integer := read_value;
begin
    mailbox <= to_integer(unsigned(bump(std_logic_vector(to_unsigned(BASE, 8)))));
end architecture rtl;
