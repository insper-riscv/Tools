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
    """Check the environment, then run the clocked program."""
    for name in ("ROM_HEX", "TEST_NAME"):
        if not os.environ.get(name):
            raise AssertionError(f"{name} not set")

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    for _ in range(20):
        await RisingEdge(dut.clk)
        if int(dut.tohost.value) == 1:
            return

    raise AssertionError("tohost never reached 1")
