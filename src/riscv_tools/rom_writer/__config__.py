"""Defaults for writing a ROM image over JTAG. A project's config.yaml
overrides these under `quartus:`."""

DEFAULTS = {
    "quartus": {
        # Instance index Quartus' In-System Memory Content Editor
        # assigns to the ROM debug tap, in declaration order in the
        # project. 0 is the common case (ROM instantiated first).
        "rom_mem_instance": 0,
    },
    "memory": {
        # ROM depth (in words) — project-specific, no sane default.
        # Used to validate/format a program's .mif before writing it.
        "rom_words": None,
    },
}
