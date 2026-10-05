# Reads and writes words of the SDRAM through its debug port (a Virtual JTAG instance with a
# 64-bit DEBUG register, see Memory's docs/SDRAM_DEBUG.md).
#
# Usage: quartus_stp -t sdram_dbg.tcl <hardware> <device> read  <word_address> <word_count>
#        quartus_stp -t sdram_dbg.tcl <hardware> <device> write <word_address> <value> [<byte_enable>]
#        quartus_stp -t sdram_dbg.tcl <hardware> <device> fill  <word_address> <word_count> <value>
#
# A word address counts 32-bit words from the base of the SDRAM. read prints WORDS=<values,
# in decimal, separated by spaces>; write and fill print OK.
package require ::quartus::jtag

if {[llength $argv] < 3} {
    puts stderr "Usage: quartus_stp -t sdram_dbg.tcl <hardware> <device> read|write|fill <args>"
    exit 1
}
lassign $argv HW DEV CMD
set ARGS [lrange $argv 3 end]

# commands of the DEBUG register (op field)
set OP_STATUS 0
set OP_READ 1
set OP_WRITE 2
set OP_FILL 3
set OP_COUNT 4
set OP_READ_NEXT 5

set BUSY 1
set ERROR 2
set INITIALIZED 4
set MAX_POLLS 400

proc fail {code message} {
    puts stderr $message
    catch { device_unlock }
    catch { close_device }
    exit $code
}

# one shift of the DEBUG register: returns {status word data} of the previous command
proc shift {op word data be} {
    set v [expr {($op << 60) | ($be << 56) | (($word & 0xFFFFFF) << 32) | ($data & 0xFFFFFFFF)}]
    set r [device_virtual_dr_shift -instance_index 0 -length 64 \
               -dr_value [format %016llx $v] -value_in_hex]
    scan $r %llx x
    return [list [expr {($x >> 56) & 0xFF}] [expr {($x >> 32) & 0xFFFFFF}] [expr {$x & 0xFFFFFFFF}]]
}

# shifts until the previous command has finished: returns its {status word data}
proc settle {} {
    global OP_STATUS BUSY ERROR MAX_POLLS
    for {set i 0} {$i < $MAX_POLLS} {incr i} {
        lassign [shift $OP_STATUS 0 0 0xF] status word data
        if {!($status & $BUSY)} {
            if {$status & $ERROR} { fail 4 "the SDRAM controller did not answer" }
            return [list $status $word $data]
        }
    }
    fail 5 "the debug command never finished"
}

if {[catch {
    set hw_name $HW
    open_device -hardware_name $HW -device_name $DEV
    device_lock -timeout 10000
    device_virtual_ir_shift -instance_index 0 -ir_value 1 -no_captured_ir_value
} err]} {
    fail 2 "cannot open the debug port: $err"
}

lassign [settle] status word data
if {!($status & $INITIALIZED)} { fail 6 "the SDRAM is not initialized" }

switch $CMD {
    read {
        lassign $ARGS first count
        set words {}
        for {set i 0} {$i < $count} {incr i} {
            if {$i == 0} { shift $OP_READ $first 0 0xF } else { shift $OP_READ_NEXT 0 0 0xF }
            lassign [settle] status word data
            lappend words $data
        }
        puts "WORDS=$words"
    }
    write {
        lassign $ARGS first value be
        if {$be eq ""} { set be 0xF }
        shift $OP_WRITE $first $value $be
        settle
        puts "OK"
    }
    fill {
        lassign $ARGS first count value
        shift $OP_COUNT 0 $count 0xF
        settle
        shift $OP_FILL $first $value 0xF
        settle
        puts "OK"
    }
    default { fail 1 "unknown command $CMD" }
}

device_unlock
close_device
exit 0
