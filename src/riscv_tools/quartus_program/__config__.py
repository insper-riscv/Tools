"""Defaults for compiling+programming the base Quartus bitstream. A
project's config.yaml overrides these under `quartus:` — project_dir/
project_name/sof_file/rom_mif_target are project-specific, no sane
generic default."""

DEFAULTS = {
    "quartus": {
        "project_dir": None,
        "project_name": None,
        "sof_file": None,
        "rom_mif_target": None,
        # Directories quartus_sh's incremental compilation caches
        # under — deleted before every compile, since a ROM
        # megafunction's init_file is a string parameter, not a
        # tracked project source: changing it does NOT invalidate the
        # cache on its own.
        "stale_cache_dirs": ["db", "incremental_db", "output_files", "simulation"],
    },
}
