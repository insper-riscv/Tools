"""Define defaults for driving cocotb/GHDL simulation.

Overridden under `sim:` in a project's config.yaml.
"""

from typing import Any

DEFAULTS: dict[str, dict[str, Any]] = {
    "sim": {
        # Top-level VHDL entity GHDL elaborates and cocotb attaches to
        # — project-specific, no sane default.
        "toplevel": None,
        # VHDL source files, in dependency order — project-specific,
        # no sane default.
        "vhdl_sources": None,
        # The project's own cocotb test module (e.g. "sim.test_c_program")
        # — it knows the DUT's actual signal hierarchy (ROM/RAM memory
        # array handles, clk/rst names), which this package can't,
        # and polls the PASS/FAIL mailbox the same way mailbox.py does
        # for real hardware. No sane default.
        "test_module": None,
        # VHDL-2008 (IEEE Std 1076-2008) — matches Quartus' own
        # VHDL_INPUT_VERSION ceiling (confirmed against Quartus
        # 25.1std: VHDL_2019 is rejected as an illegal assignment
        # value, VHDL93/VHDL_2008 are the only accepted options), so
        # simulation and synthesis stay on the same dialect.
        "ghdl_std": "08",
        # VHDL generics to set on toplevel at GHDL's run step (see
        # sim_runner.run_test) — e.g. a project whose sim-only ROM
        # model loads its program image via a `ROM_FILE` generic
        # (rather than sim_runner's own ROM_HEX/TEST_NAME env vars)
        # sets {"ROM_FILE": "{hex_path}"} here; "{hex_path}" is
        # substituted with this test's compiled .hex path (see
        # run_suite). Empty by default — most toplevels need no
        # generic overrides at all.
        "parameters": {},
    },
}
