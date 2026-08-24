"""Defaults for zeroing RAM over JTAG.."""

DEFAULTS = {
    "quartus": {
        # Instance index Quartus' In-System Memory Content Editor
        # assigns to the RAM debug tap. 1 is the common case (RAM
        # instantiated right after ROM).
        "ram_mem_instance": 1,
    },
    "memory": {
        # RAM depth (in words), project-specific.
        "ram_words": None,
    },
}
