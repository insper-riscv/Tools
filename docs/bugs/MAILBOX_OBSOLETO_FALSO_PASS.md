# A stale mailbox made a test that never ran look passed

## 1. Summary

The host decides that a test finished by reading its mailbox word (PASS or FAIL). Before
this fix it never cleared that word itself, so it relied on the board's boot code to do it.
When the boot code did not clear it, the host read the previous test's PASS the moment it
started the next one, and reported tests that never ran as passed.

| | |
| :--- | :--- |
| Symptom | every test of a run reports PASS in about two seconds, memory tests then fail on the golden compare |
| Cause | the mailbox keeps the previous test's value until the new test writes its own, and the host does not clear it |
| Trigger found | the board held the boot ROM of another platform, which cleared the mailbox at the old address, not the one of the SDRAM platform |
| Fix | the host sets the mailbox to 0 before it loads and starts each test |
| What caught it | the golden compare of the memory tests disagreed with the PASS: a PASS that comes with a golden mismatch is a sign of this |

## 2. The mechanism

A run of the suite loads a test, starts it and polls the mailbox until it reads PASS (1) or
FAIL (2). Between two tests the core is parked in a wait loop and the mailbox still holds the
last result.

1. The boot code is meant to clear the mailbox every time the core restarts, so the next
   poll sees 0 until the new test finishes.
2. If the boot code clears some other address, nothing clears the mailbox.
3. The host loads the next test and starts it; its first poll reads the old PASS and ends
   the test at once.
4. The same happens to every later test. Tests without a golden (unit tests) stay green; tests
   with a golden fail, because the memory they were judged on was never written by them.

## 3. The fix

The host writes 0 to the mailbox before it writes the next test's image and starts it, so a
test is judged only by what it writes after it starts. It works with either way of reaching
the RAM (a memory instance of the FPGA or the SDRAM debug port).

## 4. How to avoid it

A host that waits for a flag from the target must reset the flag itself and not depend on
code that runs on the target. A run whose tests all finish in the same short time, or whose
unit tests all pass while its memory tests fail, deserves a second look before it is
believed.
