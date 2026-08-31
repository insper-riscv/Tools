"""Defaults for writing a ROM image over JTAG."""

DEFAULTS = {
    "quartus": {
        # Instance index/indices Quartus' In-System Memory Content
        # Editor assigns to the ROM debug tap(s), in declaration order
        # in the project. [0] is the common case (a single ROM
        # instantiated first) — a project with more than one physical
        # ROM copy (see rom_writer.write_rom's docstring) lists every
        # one here, in the order they must all be kept in sync.
        "rom_mem_instances": [0],
    },
    "memory": {
        # ROM depth (in words), project-specific.
        # Used to validate/format a program's .mif before writing it.
        "rom_words": None,
    },
}
