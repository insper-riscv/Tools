# The host gave up on a fill of the whole SDRAM after a fraction of a second

## 1. Summary

The script that sends a command to the SDRAM debug port waited for the command to finish by
polling the status a fixed number of times. A fill of the whole SDRAM runs for about two
seconds, longer than that wait, so the script gave up with an error while the board was still
filling.

| | |
| :--- | :--- |
| Symptom | `zero-ram` failed with "the debug command never finished" although the board kept filling |
| Cause | the wait was a count of 400 status reads, about 0.4 s, for every command alike |
| Fix | the wait is a time limit: 3 s for a read or a write, 60 s for a fill |
| Check on the board | the first, a middle and the last word of the SDRAM hold values, `zero-ram` takes 2.4 s, and all three read 0 |

## 2. The mechanism

A status read through JTAG costs about a millisecond, so a limit counted in reads is a limit in
time that depends on the cable. A fill is run by the board and its duration is set by the
controller: about 15 clocks of 7 ns per word, so $2^{24}$ words take

$$
2^{24} \cdot 15 \cdot 7\,\text{ns} \approx 1.8\,\text{s}.
$$

The script stopped polling after 0.4 s, reported the error, and left the fill running.

## 3. The fix

The wait is a deadline in milliseconds. Commands that are one access keep a short one (a
dead controller is noticed quickly); a fill gets a long one.

## 4. How to avoid it

A timeout for an operation whose length grows with its argument must grow with it, and a
limit written as a number of polls hides the unit that matters. It only showed on the largest
fill, which is why the smaller ones used in the first tests passed.
