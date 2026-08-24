"""cocotb test that always FAILS.

Used by tests/test_sim_runner.py to verify sim_runner.run_test
returns False (not an exception) on a failing run, matching how a
real FAIL should surface as one failed manifest entry rather than
crashing the whole suite.
"""

from typing import Any

import cocotb


@cocotb.test()
async def test_program(dut: Any) -> None:
    assert False, "deliberately fails, see tests/test_sim_runner.py"
