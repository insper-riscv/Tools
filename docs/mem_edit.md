# `mem_edit`

Generic In-System Memory Content Editor primitives, shared by [`rom_writer`](rom_writer.md), [`ram_zero`](ram_zero.md), [`ram_dump`](ram_dump.md), and [`mailbox`](mailbox.md). Pure mechanism, no policy: each of those modules decides which instance, address, or content to use; this module only knows how to read/write a memory instance over JTAG.

## Functions

| Function | Does |
| :--- | :--- |
| `write_full` | Overwrite a memory instance's entire depth from a `.mif`. |
| `write_full_multi` | Same, but writes the same `.mif` to several instances in one call (a design with more than one physical copy of the same content, kept in sync). |
| `write_word` | Overwrite a single word at a given offset. |
| `read_words` | Read back a range of words. |
| `dump` | Save an instance's entire content to a `.mif`. |

## Configuration

None: takes a `JtagLink` (see [`jtag`](jtag.md)), an instance index, and paths/addresses as direct arguments; no `config.yaml` section of its own. Callers decide which instance index and depth apply to their own use case.

## Usage

Not its own CLI subcommand: it's the mechanism [`rom_writer`](rom_writer.md), [`ram_zero`](ram_zero.md), [`ram_dump`](ram_dump.md), and [`mailbox`](mailbox.md) each call to actually talk to a memory instance over JTAG.
