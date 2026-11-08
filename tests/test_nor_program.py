"""nor_program: the map of the programmer and the image of a bank."""

import pytest
from support import check_equal

from riscv_tools import nor_program
from riscv_tools.nor_program import core

CFG = {
    "memory": {
        "ram_base": 0x40000000,
        "ram_words": 1 << 24,
        "tohost_addr": 0x43FFFFE8,
        "rom_base": 0x1000,
    }
}


def test_the_layout_keeps_the_job_below_the_image() -> None:
    """The job sits 32 bytes before the image, inside the RAM."""
    layout = nor_program.layout_of(CFG)
    check_equal(layout.image - layout.job, 32)
    check_equal(layout.ram_end, 0x44000000)
    check_equal(layout.program, 0x40100000)


def test_the_data_of_the_programmer_ends_at_the_stdout_buffer() -> None:
    """The linker may use the RAM up to the stdout buffer."""
    layout = nor_program.layout_of(CFG)
    check_equal(layout.data + layout.data_size, 0x43FFFBE0)


def test_the_bank_image_is_the_header_and_the_payload_in_whole_pages() -> None:
    """The size in the header gives the end; the page is 256 bytes."""
    words = [0] * 2048
    words[1024 : 1024 + 5] = [0x52564946, 300, 0, 1, 0]
    image = nor_program.load_bank_image(words, 0x1000)
    check_equal(len(image), 768)
    check_equal(image[:4], bytes.fromhex("46495652"))
    check_equal(image[256 + 300 :], b"\xff" * (768 - 556))


def test_an_image_without_header_page_is_refused() -> None:
    """A FLASH shorter than the header page has no image."""
    with pytest.raises(ValueError, match="header"):
        nor_program.load_bank_image([0] * 1025, 0x1000)


def test_the_words_of_a_block_are_padded_with_ff() -> None:
    """A block that ends in half a word is completed with 0xFF."""
    check_equal(
        core.words_of(b"\x01\x02\x03\x04\x05"), [0x04030201, 0xFFFFFF05]
    )
