# `board`

Finds out which board is plugged into the host, chooses the right board for a platform, locks it for exclusive use and tells which cable to use. The reading of `jtagconfig` is the one of the [`jtag`](jtag.md) module (`read_cables`); this module only interprets what it returns.

## 1. Reference

The JTAG identification plan (`Plans/Multi-FPGA/03-IDENTIFICACAO-PELO-JTAG.md`) defines the algorithm, the nine ambiguity cases and the per-board lock. The known boards come from the catalog read by the `board_schema` module (`Catalog`, packages `boards/<board>/board.yaml` of Insper-RISC-V); only the `jtag` part is used here.

```yaml
board: de0-cv
device: 5CEBA4F23C7
jtag:
  cable: usb-blaster      # usb-blaster-ii, samd21-usbblaster, external
  chain: [{name: "5CE(BA4|FA4)", idcode: "02B050DD", fpga: true}]
```

## 2. What identifies a board

A board is the pair (chain IDCODE, stable path of the USB port). The IDCODE says what the board can be, and the port says which of the candidates it is.

| Source | Use |
| :--- | :--- |
| IDCODE without the 4 version bits | Candidates of the chain; `031050DD` does not tell `10M50DA` from `10M50DC`, and the module warns |
| udev `ID_PATH` of the port (`pci-0000:00:14.0-usb-0:2`) | Disambiguation key; without `udevadm`, the position under `/sys/devices` with the prefix `sys:` serves |
| Cable name (`USB-Blaster [1-2]`) | Only the `-c` argument of the session, never a key |
| USB serial number | Discarded, because the same value shows up on several cables |

The chain of a candidate is compared with the one of the `board.yaml` by rule V17 of the validator (`board_check.check_chain`), the same function that checks the platform. The `DE-SoC` and `USB-BlasterII` cables are of kind `usb-blaster-ii`, and the others are `usb-blaster`.

## 3. Host inventory

The inventory ties a USB port to a board. It is read from `~/.config/riscv-tools/boards.yaml`, or from `/etc/riscv-tools/boards.yaml`, and the first one that exists applies.

```yaml
host: ws
lock_dir: /tmp
boards:
- {id: de0-cv-ws, board: de0-cv, usb_path: "pci-0000:00:14.0-usb-0:2"}
- {id: de2-115-ws, board: de2-115, usb_path: "pci-0000:00:14.0-usb-0:3"}
```

Without the file, a board with a single candidate is still identified, and the `host` is the short machine name or the value of `RISCV_TOOLS_HOST`. The command `board scan --save` records the certain cables; a cable with several candidates asks for `--assign PORT=BOARD`.

## 4. Subcommands

| Command | Effect |
| :--- | :--- |
| `board scan [--save] [--assign PORT=BOARD] [--json]` | Lists each cable with chain, port, possible boards and inventory entry |
| `board select [--cable C] [--board-id I] [--board B] [--platform platform.yaml] [--free] [--all] [--json]` | Chooses the board and the cable; `--all` lists every present one |
| `board lock <select options> [--wait [S]] (-- command \| --hold)` | Selects, locks and runs the command under the lock, or holds the lock until standard input closes |
| `board doctor [--json]` | Checks cable, chain, processes and the special boards, changing nothing |

The location options are `--boards-dir` (repeatable, the `boards/` folder of a catalog, besides `RISCV_TOOLS_BOARDS`, `<root>/boards` and `<root>/Insper-RISC-V/boards`), `--inventory` and `--host`.

The output of `select` carries `board`, `id`, `cable`, `device` (the `@N: name (0xIDCODE)` identity of the FPGA on the chain, in the format of `quartus.jtag_device`), `idcode`, `port`, `lock_file`, `warnings` and `free`. The exit code is 2 for a selection error, with the case number, and 3 when every board is busy.

## 5. Selection precedence

From the strongest source to the weakest the order is `--cable`, `--board-id`, `--board`, the `board:` of the `platform.yaml` and `auto`. The first three also exist as global options (`riscv-tools --board X run`) and as the variables `RISCV_TOOLS_CABLE`, `RISCV_TOOLS_BOARD_ID` and `RISCV_TOOLS_BOARD`.

| Source | Effect |
| :--- | :--- |
| `--cable` | Forces the cable and dispenses with the inventory; the chain is still checked against the expected board |
| `--board-id` | Picks the inventory entry and checks the cable of its port |
| `--board` or `board: <name>` | Fixes the board and chooses among the cables that present it |
| `board: auto` | Chooses among the present and free boards of `boards:` |

Two equal candidates with no tie-break are a case 2 error with the list of cables. The `--free` option picks, among equal ones, the first free in port order, and never the listing order of `jtagconfig`.

## 6. The nine cases

| # | Case | Result |
| :--- | :--- | :--- |
| 1 | One cable, one candidate | Chosen |
| 2 | Two equal boards on the same host | Error with the list of cables, or the inventory (or `--free`) breaks the tie |
| 3 | Equal boards on different hosts | Each host has its own inventory and the `id` carries the host name |
| 4 | Same IDCODE for different devices | Candidates are the boards that cite the IDCODE; variant warning |
| 5 | Same device on different boards | The inventory, or `--board`, breaks the tie |
| 6 | Revisions of the same device | Warning that the IDCODE does not prove the variant |
| 7 | Unknown IDCODE | Error with the IDCODEs searched and the cables seen |
| 8 | Broken chain | Infrastructure error; only powering the board off and on fixes it |
| 9 | Busy cable | The lock refuses and shows the owner; `--wait` waits |

## 7. Per-board lock

Each board has a lock file, taken with an exclusive `flock` for the whole session. The name is the board identifier without hyphens plus the host (`de0cv-ws.lock`), the file that the agents and the Tests runner already use. A host with two boards of the same kind uses the inventory `id`, and an entry can fix the file with `lock_file`.

The owner writes the host, the user, the process, the command and the time into the file. Whoever finds the board busy reads that record; a plain `flock` records nothing, and the message says so. Without `--wait` the lock fails at once, and `--wait` alone waits up to 4 hours.

## 8. Boards without a standard USB-Blaster

The DE10-Nano uses the USB-Blaster II, with the cable `DE-SoC [USB-1]` and a chain of two devices, the HPS (`4BA00477`) and the FPGA (`02D020DD`). The FPGA is the second on the chain, and the device identity uses position `@2`. The `doctor` warns about firmware not yet loaded (`09fb:6010`), about a cable that does not show up (`09fb:6810` with no `DE-SoC` cable) and suggests removing the HPS from the chain in the programmer on error 209025, without applying anything.

The MKR Vidor 4000 only has the USB of the SAMD21 (`2341:8056`). The `doctor` says that the `USBBlaster` sketch must be loaded into the SAMD21 through the bootloader mode, and the tools do not write the sketch.

## 9. Configuration integration

`riscv-tools` builds the `JtagLink` through the selection when `quartus.jtag_device` is not set, or when `--board` or `--board-id` is given. With `jtag_device` and neither option, the cable is the one that lists its IDCODE, or the one that `--cable` forces, as long as its chain lists the IDCODE. The keys `quartus.board` (identifier or `auto`) and `quartus.boards` (list that `auto` may take) come from the `platform.yaml`.

## 10. Tests

The tests use fixtures of `jtagconfig` (`tests/fixtures/jtagconfig`), of `lsusb` and of board packages (`tests/fixtures/boards`), with no board or Quartus. They cover cases 1, 2, 4, 5, 6, 7, 8 and 9, the precedence, the inventory registration, the lock against an external `flock`, the subcommands end to end and the handling of the DE10-Nano and the MKR Vidor.

```bash
uv run pytest tests/test_board_scan_select.py tests/test_board_special.py \
  tests/test_board_lock.py tests/test_board_cli.py
```

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../../LICENSE).
