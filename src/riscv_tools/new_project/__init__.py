"""Create a project: a platform for a known board, in a new checkout."""

from riscv_tools.new_project.build import (
    Created,
    create_platform,
    generation_steps,
    run_steps,
)
from riscv_tools.new_project.fetch import DEFAULT_SOURCE, REPO_FOLDER, clone
from riscv_tools.new_project.guide_text import (
    LANGUAGES,
    Summary,
    render_help,
)
from riscv_tools.new_project.naming import check_slug, check_title, slugify
from riscv_tools.new_project.peripherals import parse_peripherals
from riscv_tools.new_project.readme import write_readme
from riscv_tools.new_project.spec import (
    ProjectSpec,
    parse_cache,
    parse_size,
    validate,
)

__all__ = [
    "DEFAULT_SOURCE",
    "LANGUAGES",
    "REPO_FOLDER",
    "Created",
    "ProjectSpec",
    "Summary",
    "check_slug",
    "check_title",
    "clone",
    "create_platform",
    "generation_steps",
    "parse_cache",
    "parse_peripherals",
    "parse_size",
    "render_help",
    "run_steps",
    "slugify",
    "validate",
    "write_readme",
]
