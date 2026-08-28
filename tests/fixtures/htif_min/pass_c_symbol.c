/* Writes a known pattern into a named C global, so
 * tests/test_generate_golden.py can verify golden_generator.symbol_range
 * resolves both its address and size correctly from the ELF, instead
 * of a human passing --start/--end by hand. */
volatile unsigned int results[2];

int main(void) {
    results[0] = 0xAABBCCDD;
    results[1] = 0x11223344;
    return 0;
}
