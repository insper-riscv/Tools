# Board identification in the laboratory

## 1. Reference

This document records the observation, on hardware, of the nine ambiguity cases of section 5 of the Multi-FPGA plan's `03-IDENTIFICACAO-PELO-JTAG.md`, with the `riscv-tools board scan`, `select`, `lock` and `doctor` subcommands described in [`board`](modules/board.md). The commands only read: no board was programmed and no cable was touched.

## 2. Hardware and method

| Host | Cables | USB port (`ID_PATH`) |
| :--- | :--- | :--- |
| Laptop | DE0-CV `02B050DD` | `pci-0000:00:14.0-usb-0:6` |
| PC1 | DE0-CV `02B050DD` | `pci-0000:00:14.0-usb-0:2` |
| PC1 | DE2-115 `020F70DD` | `pci-0000:00:14.0-usb-0:3` |
| PC1 | DE0-Nano `020F30DD` | `pci-0000:00:14.0-usb-0:5` |
| PC1 | DE10-Lite `031050DD` | `pci-0000:00:14.0-usb-0:6` |
| PC1 | MKR Vidor 4000, only `2341:8056` on the USB | no cable |

The DE10-Nano does not enumerate, so it only appears through fixtures. The four cables of PC1 show the same `iSerial` (`91d28408`) on different ports, which confirms that the serial number does not identify the board and that the `ID_PATH` does.

Each case has one of two origins.

| Origin | Meaning |
| :--- | :--- |
| Real | The `jtagconfig` and USB output is that of the connected hardware |
| Simulated | A `jtagconfig` wrapper changes, in the real text, only the line of the affected cable (another IDCODE, a broken chain, a missing cable), because the laboratory has neither a second equal board on the same host nor a way to break a chain without touching the physical cable. The cable, the port and the `udev` reading stay real |

## 3. The nine cases

| # | Case | Origin | Command | Observed result |
| :--- | :--- | :--- | :--- | :--- |
| 1 | One cable, one candidate | Real | `board select` on the laptop | `de0-cv`, id `de0-cv-laptop`, exit 0 |
| 2 | Two equal boards on one host | Simulated | `board select` with `[1-3]` showing `02B050DD` | Case 2 error with the list of cables and ports; `--board-id`, `--cable` and `--free` break the tie; `scan --save` numbers the second as `de0-cv-ws-2` |
| 3 | Equal boards on different hosts | Real | `board select` on the laptop and on PC1 | Each host picks its own DE0-CV; the id carries the host name (`de0-cv-laptop`, `de0-cv-ws`) and so does the lock (`de0cv-laptop.lock`, `de0cv-ws.lock`) |
| 4 | Same IDCODE, different devices | Real | `board select --board de2-115`, `de0-nano` | Picked by IDCODE, with the warning that `020F70DD` and `020F30DD` do not prove the variant |
| 5 | Same device, different boards | Fixture | `pytest tests/test_board_scan_select.py` | `--board` or the inventory breaks the tie; the laboratory has only one board per EP4CE22 IDCODE |
| 6 | Revisions of one device | Real | `board select --board de10-lite` | Warning that `031050DD` does not tell `10M50DA` from `10M50DC` |
| 7 | Unknown IDCODE or missing board | Real and simulated | `--board de2-115` on the laptop; cable `[1-3]` removed; IDCODE `0123ABCD` | Case 7 error with the IDCODEs searched and the cables seen; with an inventory, `no cable at <port>` or `IDCODE mismatch`; with no cable at all, `searched IDCODEs ...; cables seen: no cable` |
| 8 | Broken chain | Simulated | `board scan`, `select`, `doctor` | `scan` flags the problem on the port and the other boards stay selectable; `select --board de2-115` fails with case 8; `doctor` asks to power the board off for 10 s and on again |
| 9 | Busy cable | Real | `board lock` in two processes, a stray `quartus_stp` | See section 5 |

## 4. Selection

All results below come from PC1 with the four boards connected and from the laptop with one.

| Form | Observed |
| :--- | :--- |
| No option, four distinct boards | Case 2 error, `4 boards match`, with board, cable and port of each |
| `--board <name>` | Each of the four picks the right cable; `--board mkr-vidor-4000` and `--board de10-nano` fail with case 7 |
| `--cable "<name>"` | Picks the board by the cable's IDCODE; a nonexistent cable fails with case 7, and the DE0-CV cable with `--board de2-115` fails with `expects IDCODE 020F70DD ... the chain has 02B050DD` |
| `--board-id <id>` | Picks the inventory entry; an unknown id lists the known ids |
| `--platform` | `board: auto` with `boards: [de2-115]` picks the DE2-115; `--board` beats the platform field; the Vidor platform fails with case 7 |
| Precedence | `--board-id` beats `--board`; `--cable` beats the inventory, but the cable's IDCODE is still checked against the board `--board` asks for |
| `--free` | Picks the first free board in port order, never in `jtagconfig` order |

## 5. Lock with owner and contention

The lock was tested with two and three processes, in an isolated lock folder (`lock_dir`), so as not to compete with the agents that hold `/tmp/de0cv-*.lock`.

| Situation | Result |
| :--- | :--- |
| Process A holds the DE0-CV with `--hold` | The lock file records host, user, process, command and instant |
| B asks for the same board without `--wait` | Fails at once with case 9, the owner (`user@host`, pid, since when) and its command; exit 3 |
| B asks for the same board with `--wait 3` | Waits the 3 s and fails with the same owner |
| B asks for the same board with `--wait 20` and the owner lets go in 5 s | Gets in after 5.5 s |
| C asks for the DE10-Lite while A holds the DE0-CV | Gets in: the lock is per board, not per cable or per host |
| The owner is a plain `flock` | Fails with `held by an owner that did not record itself (a plain flock)` |
| `select` while the board is busy | Case 9 error with the owner, or `free: false` with `--all` |
| `doctor` while the board is busy | Shows the lock owner |
| A stray `quartus_stp` process running | `doctor` warns `process <pid>` with the case 9 hint |

## 6. Cable moved to another port

The `ID_PATH` is the key, and the cable name is only the argument of `-c`. Two swaps were simulated in the inventory, with the real cables of PC1 on their usual ports.

| Swap | Result |
| :--- | :--- |
| The DE2-115 cable shows on `:3` and the inventory has it on `:7` | The cable on `:3` shows with no entry, `select --board de2-115` finds it by IDCODE, `--board-id` fails with `no cable at :7`, `doctor` warns about both ports, and `scan --save` changes the port of the existing entry without creating a second one |
| DE0-CV and DE2-115 swapped between ports | `IDCODE mismatch` on both ports, in `scan`, `select --board-id` and `doctor` (rule V17), without picking the wrong board |

## 7. What the laboratory does not cover

| Item | Reason |
| :--- | :--- |
| Two DE0-CV on one host | The two boards are on different hosts; case 2 was simulated and is in a fixture test |
| A truly broken chain | Needs touching the power or the cable of the board |
| Physically moving a cable to another port | Needs touching the cable; the swap was simulated in the inventory |
| DE10-Nano and Vidor with a chain | The DE10-Nano does not enumerate and the Vidor only shows the SAMD21 USB; both cases are in fixture tests |

---

Copyright 2026 Insper. Licensed under the [Apache License, Version 2.0](../../LICENSE).
