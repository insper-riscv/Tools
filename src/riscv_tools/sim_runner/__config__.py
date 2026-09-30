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
        # sets {"ROM_FILE": "{hex_path}"} here. Templates may use
        # {hex_path} and {mif_path} (this test's image, whichever
        # sim.image selects; the other is empty) and
        # {boot_rom_hex_path} and {boot_rom_mif_path} (the boot ROM's,
        # the same for every test). See run_suite. Empty by default —
        # most toplevels need no generic overrides at all.
        "parameters": {},
        # Format of the .hex a simulation loads: "words" is one 32-bit
        # word per line, with leading zero words so a program linked
        # above address 0 lands at its real word index; "verilog" is
        # what `objcopy -O verilog` writes, with `@<word address>`
        # lines and four words per line, so the memory model loading it
        # must understand both.
        "hex_format": "words",
        # Which image a simulation loads, and so which manifest `sim`
        # reads by default: "hex" is <build_dir>/sim/manifest.json (from
        # `compile --emit hex`), "mif" is <build_dir>/real/manifest.json
        # (from `compile --emit mif`), the same images the hardware
        # loads. With "mif", `sim` also builds the boot ROM's .mif
        # (`{boot_rom_mif_path}` below).
        "image": "hex",
        # Extra arguments for GHDL's analyze, elaborate and run steps,
        # e.g. ["-fsynopsys", "-fexplicit"] for a vendor simulation
        # library that needs them.
        "ghdl_flags": [],
        # VHDL libraries to analyze once per `sim` run, before
        # vhdl_sources, as {library name: [source files]} (e.g.
        # Quartus' altera_mf, for a toplevel that instantiates its
        # memory IP). `$VAR` and `${VAR}` in a path are replaced from
        # the environment; an unset variable is an error.
        "libraries": {},
        # Files copied into each test's run directory (the simulator's
        # working directory) before it runs, as {file name: source},
        # for a design that opens a file by a fixed name (e.g. an
        # altsyncram `init_file`). The source is a template, see
        # `parameters` for the names.
        "run_files": {},
        # Extra environment variables for the project's test module, as
        # {name: template}; same templates as `parameters`.
        "env": {},
    },
}
