"""Define defaults for editing a project's PLL clock frequency.

A project's config.yaml overrides these under `freq_sweep:`. Every
key here describes the *shape* of the PLL source's parameter strings
— nothing here is a sane cross-project default, since PLL megafunction
instance names/parameter conventions are project-specific.
"""

DEFAULTS = {
    "freq_sweep": {
        # Path (relative to the project root) to the Verilog/VHDL PLL
        # source orchestrator.run_freq_sweep_at rewrites before each
        # compile. Project-specific, no sane default.
        "pll_file": None,
        # How many equally phase-spaced clock outputs the PLL
        # instance has (e.g. 3 for a 0/120/240-degree three-way PLL).
        # 1 (a plain single-phase PLL) is the sane default — most
        # projects don't need multi-phase clocking.
        "phase_count": 1,
        # "{idx}"-templated parameter names (0-indexed) this module
        # searches for and rewrites, e.g. Quartus' altpll megafunction
        # uses "output_clock_frequency0/1/2..." and
        # "phase_shift0/1/2...". Override if your PLL wraps a
        # different megafunction/instance naming.
        "freq_param_template": "output_clock_frequency{idx}",
        "phase_param_template": "phase_shift{idx}",
        # The literal unit suffix written after the frequency/phase
        # value (e.g. `.output_clock_frequency0("10.000000 MHz")`).
        # Note the period/phase-offset math itself is always computed
        # in MHz/ps terms (matching Quartus' altpll convention) — these
        # two keys only control what string suffix gets written, not
        # the arithmetic.
        "freq_unit": "MHz",
        "phase_unit": "ps",
    },
}
