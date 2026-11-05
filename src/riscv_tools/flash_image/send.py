"""Send an image to the program that receives it, over the JTAG UART."""

from collections.abc import Callable

from riscv_tools import uart_console
from riscv_tools.jtag import JtagLink

CHUNK = 16384
_SETTLE_SECONDS = 0.001

Reader = Callable[..., bytes]


def send_image(
    link: JtagLink,
    image: bytes,
    on_bytes: Callable[[bytes], None],
    reader: Reader = uart_console.read_console,
) -> int:
    """Give the bytes of an image to the program, in order.

    The program reads the header first and then as many payload bytes
    as the header says, so the stream is the image itself with no
    framing. What the program prints meanwhile goes to `on_bytes`.

    Parameters
    ----------
    link : JtagLink
        Which JTAG cable/chip to send through.
    image : bytes
        The packed image.
    on_bytes : callable
        Called with each chunk the program prints.
    reader : callable, optional
        The UART scan (`uart_console.read_console`); replaced in tests.

    Returns
    -------
    int
        How many bytes were sent.
    """
    for start in range(0, len(image), CHUNK):
        reader(
            link,
            on_bytes,
            seconds=_SETTLE_SECONDS,
            send=image[start : start + CHUNK],
        )
    return len(image)
