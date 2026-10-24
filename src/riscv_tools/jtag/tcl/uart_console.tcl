# Reads what the program prints through the JTAG UART (a Virtual JTAG instance with a 48-bit
# register, see Memory's docs/EXTERNAL_BUS.md), and optionally sends bytes to it.
#
# Usage: quartus_stp -t uart_console.tcl <hardware> <device> <seconds> [<hex bytes to send>]
#        quartus_stp -t uart_console.tcl <hardware> <device> <seconds> -
#
# Scans back to back for <seconds> seconds (0 = until the process is killed). Every time bytes
# arrive it prints a line BYTES=<hex digits> and flushes, so a reader sees the output as it is
# produced. The bytes to send go one per scan, first thing. With "-" instead of the bytes, the
# script reads lines of hex digits from its standard input as it scans and sends their bytes,
# one per scan, until the input ends and the program has been quiet for a second and a half
# (interactive use: the reader types, the program answers).
package require ::quartus::jtag

if {[llength $argv] < 3} {
    puts stderr "Usage: quartus_stp -t uart_console.tcl <hardware> <device> <seconds> [<hex bytes>]"
    exit 1
}
lassign $argv HW DEV SECONDS
set SEND {}
set INTERACTIVE 0
if {[llength $argv] > 3 && [lindex $argv 3] eq "-"} {
    set INTERACTIVE 1
    fconfigure stdin -blocking 0
} elseif {[llength $argv] > 3} {
    set hex [lindex $argv 3]
    for {set i 0} {$i + 1 < [string length $hex]} {incr i 2} {
        lappend SEND [scan [string range $hex $i [expr {$i + 1}]] %x]
    }
}
# the UART is the second Virtual JTAG instance; the SDRAM debug port is the first
set INSTANCE 1

proc fail {code message} {
    puts stderr $message
    catch { device_unlock }
    catch { close_device }
    exit $code
}

if {[catch {
    open_device -hardware_name $HW -device_name $DEV
    device_lock -timeout 10000
    device_virtual_ir_shift -instance_index $INSTANCE -ir_value 1 -no_captured_ir_value
} err]} {
    fail 2 "cannot open the UART: $err"
}

proc read_typed {} {
    # the hex digits the reader has typed since the last scan, as a list of bytes; sets done at the end of the input
    global SEND INPUT_DONE
    while {[gets stdin hex] >= 0} {
        for {set i 0} {$i + 1 < [string length $hex]} {incr i 2} {
            lappend SEND [scan [string range $hex $i [expr {$i + 1}]] %x]
        }
    }
    if {[eof stdin]} { set INPUT_DONE 1 }
}

set INPUT_DONE 0
set last [clock milliseconds]
set end [expr {$SECONDS > 0 ? [clock milliseconds] + int($SECONDS * 1000) : 0}]
while {1} {
    if {$INTERACTIVE} {
        read_typed
        if {$INPUT_DONE && [llength $SEND] == 0 && [clock milliseconds] - $last > 1500} { break }
        if {[llength $SEND] > 0} { set last [clock milliseconds] }
    }
    set v 0
    if {[llength $SEND] > 0} {
        set v [expr {0x100 | [lindex $SEND 0]}]
        set SEND [lrange $SEND 1 end]
    }
    set r [device_virtual_dr_shift -instance_index $INSTANCE -length 48 \
               -dr_value [format %012llx $v] -value_in_hex]
    scan $r %llx x
    set n [expr {($x >> 32) & 7}]
    if {$n > 0} {
        set out ""
        for {set i 0} {$i < $n} {incr i} {
            append out [format %02x [expr {($x >> (8 * $i)) & 0xFF}]]
        }
        puts "BYTES=$out"
        flush stdout
        set last [clock milliseconds]
    }
    if {$end != 0 && [clock milliseconds] >= $end && [llength $SEND] == 0} { break }
}
catch { device_unlock }
catch { close_device }
