# Reads or writes the display register of the platform (a Virtual JTAG instance with a 25-bit
# register, see Memory's seg_display).
#
# Usage: quartus_stp -t display.tcl <hardware> <device> read
#        quartus_stp -t display.tcl <hardware> <device> write <24-bit value in hex>
#        quartus_stp -t display.tcl <hardware> <device> check <count>
#        quartus_stp -t display.tcl <hardware> <device> fail read|set|clear
#
# Prints VALUE=<six hex digits>: the register as it was when the scan started. After a write, a
# second scan reads it back, so the line shows what the register holds now.
#
# "check" writes <count> pseudo-random values, reading each back after the write has crossed to
# the core clock, and prints CHECKED=<count> MISMATCHES=<how many differed>.
package require ::quartus::jtag

if {[llength $argv] < 3} {
    puts stderr "Usage: quartus_stp -t display.tcl <hardware> <device> read|write [<hex value>]"
    exit 1
}
lassign $argv HW DEV MODE
# the display is the third Virtual JTAG instance; the SDRAM debug port and the UART come first
set INSTANCE 2

proc fail {code message} {
    puts stderr $message
    catch { device_unlock }
    catch { close_device }
    exit $code
}

proc scan_register {word} {
    global INSTANCE
    set r [device_virtual_dr_shift -instance_index $INSTANCE -length 25 \
               -dr_value [format %07x $word] -value_in_hex]
    scan $r %x x
    return [expr {$x & 0xFFFFFF}]
}

if {[catch {
    open_device -hardware_name $HW -device_name $DEV
    device_lock -timeout 10000
    device_virtual_ir_shift -instance_index $INSTANCE -ir_value 1 -no_captured_ir_value
} err]} {
    fail 2 "cannot open the display: $err"
}

# the failure flag has its own 2-bit register (instruction 2): bit 0 is the value, bit 1 writes it
if {$MODE eq "fail"} {
    if {[llength $argv] < 4} { fail 1 "fail needs read, set or clear" }
    switch -- [lindex $argv 3] {
        read  { set word 0 }
        set   { set word 3 }
        clear { set word 2 }
        default { fail 1 "fail needs read, set or clear" }
    }
    device_virtual_ir_shift -instance_index $INSTANCE -ir_value 2 -no_captured_ir_value
    device_virtual_dr_shift -instance_index $INSTANCE -length 2 -dr_value [format %x $word] -value_in_hex
    # a second scan reads back what the flag holds now
    set r [device_virtual_dr_shift -instance_index $INSTANCE -length 2 -dr_value 0 -value_in_hex]
    scan $r %x x
    puts [format "FLAG=%d" [expr {$x & 1}]]
    catch { device_unlock }
    catch { close_device }
    exit 0
}

if {$MODE eq "check"} {
    if {[llength $argv] < 4} { fail 1 "check needs a count" }
    set count [lindex $argv 3]
    set seed 12345
    set bad 0
    for {set i 0} {$i < $count} {incr i} {
        set seed [expr {($seed * 1103515245 + 12345) & 0x7FFFFFFF}]
        set value [expr {$seed & 0xFFFFFF}]
        scan_register [expr {(1 << 24) | $value}]
        after 2
        if {[scan_register 0] != $value} { incr bad }
    }
    puts "CHECKED=$count MISMATCHES=$bad"
    catch { device_unlock }
    catch { close_device }
    exit 0
}

if {$MODE eq "write"} {
    if {[llength $argv] < 4} { fail 1 "write needs a value" }
    scan [lindex $argv 3] %x value
    if {$value < 0 || $value > 0xFFFFFF} { fail 1 "the value does not fit in 24 bits" }
    scan_register [expr {(1 << 24) | $value}]
    # the write crosses to the core clock: the readback comes after the register has taken it
    after 5
}
set v [scan_register 0]
puts [format "VALUE=%06x" $v]
catch { device_unlock }
catch { close_device }
