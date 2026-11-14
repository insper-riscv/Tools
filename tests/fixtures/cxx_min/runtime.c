/* What a C++ program needs of the platform: exit() ends in _exit(), the
 * code going to `tohost`, where Spike's HTIF reads it; and the standard
 * streams, which `std::terminate` of libstdc++ names (the real runtime
 * of a platform has them in its stdio.c). Output is discarded. */
#include <stdio.h>

volatile unsigned int tohost[2] __attribute__((aligned(64)));
volatile unsigned int fromhost[2] __attribute__((aligned(64)));

void _exit(int code)
{
    tohost[1] = 0u;
    tohost[0] = ((unsigned int)code << 1) | 1u;
    for (;;) {
    }
}

static int discard(char c, FILE *stream)
{
    (void)stream;
    return (unsigned char)c;
}

static FILE sink = FDEV_SETUP_STREAM(discard, NULL, NULL, _FDEV_SETUP_WRITE);
FILE *const stdout = &sink;
FILE *const stderr = &sink;
