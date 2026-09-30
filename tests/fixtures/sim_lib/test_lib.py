"""cocotb test for tests/test_sim_runner.py's library/run-file test.

Passes when the DUT's mailbox equals EXPECTED (an environment variable
the test sets through sim.env): the value in data.txt plus one, which
only happens if the helper library was found, data.txt was in the
working directory and the extra flags reached GHDL.
"""

import os
from typing import Any

import cocotb
from cocotb.triggers import Timer


@cocotb.test()
async def test_program(dut: Any) -> None:
    await Timer(1, unit="ns")
    expected = int(os.environ["EXPECTED"])
    assert int(dut.mailbox.value) == expected, (
        f"mailbox {int(dut.mailbox.value)}, expected {expected}"
    )
