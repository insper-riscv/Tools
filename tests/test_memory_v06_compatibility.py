"""Explicit Memory v0.6 transport and bounded bank-image loading."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from riscv_tools import bin_to_image, flash_image
from riscv_tools.jtag import JtagLink
from riscv_tools.rom_writer import core as writer
from riscv_tools.sdram_debug import stream


class SdramCompatibilityTest(unittest.TestCase):
    """Check protocol selection and safe bank-image boundaries."""

    def test_legacy_protocol_has_explicit_verified_probe(self):
        """Select the legacy probe explicitly."""
        link = JtagLink(
            "cable", "device", sdram_instance=3, sdram_protocol="memory-v0.6"
        )
        with patch.object(
            stream,
            "run_tcl",
            return_value=SimpleNamespace(stdout="INFO=00030000\n"),
        ) as run:
            caps = stream.capabilities(link)
        self.assertTrue(caps.can_load_flash)
        self.assertEqual(caps.stream_words, 0)
        self.assertEqual(
            run.call_args.args[1:], ("sdram_legacy_control.tcl", "info")
        )

    def test_default_protocol_is_unchanged(self):
        """Preserve the current protocol for other platforms."""
        with patch.object(
            stream,
            "run_tcl",
            return_value=SimpleNamespace(stdout="INFO=00000000\n"),
        ) as run:
            stream.capabilities(JtagLink("c", "d"))
        self.assertEqual(run.call_args.args[1:], ("sdram_stream.tcl", "info"))

    def test_unknown_protocol_is_rejected(self):
        """Refuse an unknown protocol before starting a JTAG session."""
        with self.assertRaises(stream.StreamError):
            stream.capabilities(JtagLink("c", "d", sdram_protocol="unknown"))

    def test_legacy_writes_use_bounded_sessions(self):
        """Transfer every word exactly once in bounded sessions."""
        link = JtagLink("c", "d", sdram_protocol="memory-v0.6")
        words = list(range(2300))
        with patch.object(stream, "load_words") as load:
            stream.stream_write(link, 100, words, 0)
        self.assertEqual(
            [c.args[1] for c in load.call_args_list], [100, 1124, 2148]
        )
        self.assertEqual(
            [len(c.args[2]) for c in load.call_args_list], [1024, 1024, 252]
        )
        self.assertEqual(
            [x for c in load.call_args_list for x in c.args[2]], words
        )

    def check_bank(self, corrupt: bool) -> None:
        """Check bounds and corruption with a padded MIF."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packed = bytearray(flash_image.pack(b"firmware", 1, 65536))
            if corrupt:
                packed[-1] ^= 1
            binary = root / "image.bin"
            binary.write_bytes(packed)
            mif = root / "image.mif"
            bin_to_image.bin_to_mif(binary, mif, depth=17408, pad_words=1024)
            cfg = {
                "flash_image": {"bank": "A"},
                "memory": {
                    "sdram_windows": {
                        "FLASH": {"base": 4096, "size": 65536, "offset": 4096}
                    }
                },
            }
            with patch.object(writer.flash_load, "load_flash") as load:
                if corrupt:
                    with self.assertRaises(flash_image.ImageError):
                        writer.write_sdram_flash(JtagLink("c", "d"), cfg, mif)
                    load.assert_not_called()
                else:
                    writer.write_sdram_flash(JtagLink("c", "d"), cfg, mif)
                    image = load.call_args.args[2]
                    self.assertEqual(image.data, bytes(packed))
                    self.assertEqual(
                        image.header_size, flash_image.HEADER_SIZE
                    )
                    self.assertEqual(image.address, 4096)

    def test_bank_padding_is_not_transferred_and_header_is_written_last(self):
        """Keep bank metadata and omit unused memory padding."""
        self.check_bank(False)

    def test_corrupt_bank_is_rejected_before_hardware_write(self):
        """Reject a damaged bank before invoking the hardware writer."""
        self.check_bank(True)


if __name__ == "__main__":
    unittest.main()
