/* Writes a known, byte-distinguishable pattern to a fixed address, so
 * tests/test_generate_golden.py can verify generate_golden reads back
 * the right bytes in the right order. */
volatile unsigned int *buf = (volatile unsigned int *)0x80000100;

int main(void) {
    buf[0] = 0xAABBCCDD;
    return 0;
}
