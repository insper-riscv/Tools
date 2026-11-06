# Writes and reads the single copy of the internal FLASH through its JTAG loader (a Virtual JTAG
# instance with a 64-bit CMD register and a STREAM register, see Memory's docs/*/rom/flash_loader.md).
#
# Usage: quartus_stp -t flash_loader.tcl <hardware> <device> halt
#        quartus_stp -t flash_loader.tcl <hardware> <device> run
#        quartus_stp -t flash_loader.tcl <hardware> <device> summary
#        quartus_stp -t flash_loader.tcl <hardware> <device> read <word_address> <word_count>
#        quartus_stp -t flash_loader.tcl <hardware> <device> load <word_address> <file> <count> <sum> <run|hold>
#
# A word address counts 32-bit words from the start of the FLASH IP. halt stops the core, run releases it (it
# restarts from the boot memory). summary prints SUMMARY=<count> <sum>, the words written since the last halt and
# their checksum. read prints WORDS=<values, in decimal, separated by spaces>. load halts the core, writes the
# words of a text file (one hexadecimal word per line) from the word address in a few long scans, each one
# opened by a start bit, compares the
# count and the checksum the loader reports with the expected ones, and releases the core when the last
# argument is run; it prints OK <count> <sum>.
package require ::quartus::jtag

if {[llength $argv] < 3} {
    puts stderr "Usage: quartus_stp -t flash_loader.tcl <hardware> <device> halt|run|summary|read|load <args>"
    exit 1
}
lassign $argv HW DEV CMD
set ARGS [lrange $argv 3 end]

# commands of the CMD register (op field)
set OP_NOP 0
set OP_HALT 1
set OP_RUN 2
set OP_READ 4
set OP_SUMMARY 5
set OP_CURSOR 6
# instructions of the Virtual JTAG instance
set IR_CMD 1
set IR_STREAM 2

set BUSY 1
set HALTED 2
set REFUSED 4
set OVERRUN 8
set DEADLINE_MS 3000
# words per scan of the STREAM register
set CHUNK_WORDS 1024

proc fail {code message} {
    puts stderr $message
    catch { device_unlock }
    catch { close_device }
    exit $code
}

# one shift of the CMD register: returns {status word data} of the previous command
proc shift {op word data} {
    set v [expr {($op << 60) | (($word & 0xFFFFFF) << 32) | ($data & 0xFFFFFFFF)}]
    set r [device_virtual_dr_shift -instance_index 0 -length 64 \
               -dr_value [format %016llx $v] -value_in_hex]
    scan $r %llx x
    return [list [expr {($x >> 56) & 0xFF}] [expr {($x >> 32) & 0xFFFFFF}] [expr {$x & 0xFFFFFFFF}]]
}

# shifts until the previous command has finished: returns its {status word data}
proc settle {} {
    global OP_NOP BUSY DEADLINE_MS
    set end [expr {[clock milliseconds] + $DEADLINE_MS}]
    while {[clock milliseconds] < $end} {
        lassign [shift $OP_NOP 0 0] status word data
        if {!($status & $BUSY)} { return [list $status $word $data] }
    }
    fail 5 "the loader command never finished"
}

proc select_ir {value} {
    device_virtual_ir_shift -instance_index 0 -ir_value $value -no_captured_ir_value
}

if {[catch {
    open_device -hardware_name $HW -device_name $DEV
    device_lock -timeout 10000
    select_ir $IR_CMD
} err]} {
    fail 2 "cannot open the loader port: $err"
}

# halts the core and waits for the loader to say so
proc halt_core {} {
    global OP_HALT HALTED
    shift $OP_HALT 0 0
    lassign [settle] status word data
    if {!($status & $HALTED)} { fail 6 "the loader did not halt the core" }
}

proc summary {} {
    global OP_SUMMARY
    shift $OP_SUMMARY 0 0
    lassign [settle] status count sum
    return [list $count $sum]
}

switch $CMD {
    halt { halt_core; puts "OK" }
    run {
        shift $OP_RUN 0 0
        settle
        puts "OK"
    }
    summary {
        lassign [summary] count sum
        puts "SUMMARY=$count $sum"
    }
    read {
        lassign $ARGS first count
        halt_core
        set words {}
        for {set i 0} {$i < $count} {incr i} {
            shift $OP_READ [expr {$first + $i}] 0
            lassign [settle] status word data
            lappend words $data
        }
        puts "WORDS=$words"
    }
    load {
        lassign $ARGS first path expected_count expected_sum after
        if {[catch {open $path r} fh]} { fail 1 "cannot open $path: $fh" }
        set words {}
        while {[gets $fh line] >= 0} {
            set line [string trim $line]
            if {$line eq ""} { continue }
            if {[scan $line %x value] != 1} { fail 1 "not a hexadecimal word: $line" }
            lappend words $value
        }
        close $fh
        halt_core
        shift $OP_CURSOR $first 0
        select_ir $IR_STREAM
        set total [llength $words]
        for {set at 0} {$at < $total} {incr at $CHUNK_WORDS} {
            set chunk [lrange $words $at [expr {$at + $CHUNK_WORDS - 1}]]
            # the scan starts with a start bit (1), then the words, the first one in the least
            # significant bits: the loader takes no word before the start bit, so the scan does
            # not depend on how many clocks the Virtual JTAG hub puts between its state flags
            # and the data
            set value 0
            foreach w [lreverse $chunk] { set value [expr {($value << 32) | $w}] }
            set value [expr {($value << 1) | 1}]
            set bits [expr {32 * [llength $chunk] + 1}]
            set hex [format %0[expr {($bits + 3) / 4}]llx $value]
            device_virtual_dr_shift -instance_index 0 -length $bits \
                -dr_value $hex -value_in_hex -no_captured_dr_value
        }
        select_ir $IR_CMD
        lassign [settle] status word data
        if {$status & $OVERRUN} { fail 7 "the loader dropped a word (status $status)" }
        if {$status & $REFUSED} { fail 7 "the loader refused a write (status $status)" }
        lassign [summary] count sum
        if {$count != $expected_count || $sum != $expected_sum} {
            fail 8 "the image arrived wrong: $count words, sum $sum; expected $expected_count words, sum $expected_sum"
        }
        if {$after eq "run"} {
            shift $OP_RUN 0 0
            settle
        }
        puts "OK $count $sum"
    }
    default { fail 1 "unknown command $CMD" }
}

device_unlock
close_device
exit 0
