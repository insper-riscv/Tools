"""cocotb test that should PASS.

Used by tests/test_sim_runner.py to verify sim_runner.run_test
returns True on a passing run, and that ROM_HEX/TEST_NAME actually
arrive via extra_env as documented.
"""

import os
from typing import Any

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


@cocotb.test()
async def test_program(dut: Any) -> None:
    assert os.environ.get("ROM_HEX"), "ROM_HEX not set"
    assert os.environ.get("TEST_NAME"), "TEST_NAME not set"

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    for _ in range(20):
        await RisingEdge(dut.clk)
        if int(dut.mailbox.value) == 1:
            return

    assert False, "mailbox never reached 1"
