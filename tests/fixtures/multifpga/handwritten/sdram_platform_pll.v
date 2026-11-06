// PLL of the SDRAM platform: one 1000 MHz VCO from the 50 MHz board clock, so the same PLL gives the
// SDRAM clock (1000 / 10 = 100 MHz) and the core clocks (1000 / 20 = 50 MHz, 1000 / 10 = 100 MHz).
// The frequency and the phase of the SDRAM clocks are the `sdram` section of platform.yaml (its checks keep this file
// equal to it): the controller runs at the clock of the core at 100 MHz, so the pin paths have 10 ns.
//
//   outclk_0  100.000 MHz, phase 0        the SDRAM controller
//   outclk_1  100.000 MHz, phase 4000 ps  the DRAM_CLK pin (measured by the Quartus timing of the 5 seeds)
//   outclk_2   50.000 MHz, phase 0        instruction memories (clk_if)
//   outclk_3   50.000 MHz, phase 8250 ps  the core and the data memories (clk_idexmem), about 148 degrees later
//                                          (the `pll` section of platform.yaml; the step of a 1000 MHz VCO is 125 ps)
`timescale 1ns/10ps
module sdram_platform_pll (
	input  wire refclk,
	input  wire rst,
	output wire outclk_0,
	output wire outclk_1,
	output wire outclk_2,
	output wire outclk_3,
	output wire locked
);

	altera_pll #(
		.fractional_vco_multiplier("false"),
		.reference_clock_frequency("50.0 MHz"),
		.operation_mode("direct"),
		.number_of_clocks(4),
		.output_clock_frequency0("100.000000 MHz"),
		.phase_shift0("0 ps"),
		.duty_cycle0(50),
		.output_clock_frequency1("100.000000 MHz"),
		.phase_shift1("4000 ps"),
		.duty_cycle1(50),
		.output_clock_frequency2("50.000000 MHz"),
		.phase_shift2("0 ps"),
		.duty_cycle2(50),
		.output_clock_frequency3("50.000000 MHz"),
		.phase_shift3("8250 ps"),
		.duty_cycle3(50),
		.pll_type("General"),
		.pll_subtype("General")
	) altera_pll_i (
		.rst	(rst),
		.outclk	({outclk_3, outclk_2, outclk_1, outclk_0}),
		.locked	(locked),
		.fboutclk	( ),
		.fbclk	(1'b0),
		.refclk	(refclk)
	);

endmodule
