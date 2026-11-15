# Controls the SDRAM debug port beyond a word per command: the capability word, the hold of the
# core, the CRC-32 computed by the board and the burst registers (see docs/pt-br/modules/sdram_debug.md,
# section "Contrato com o Memory").
#
# Usage: quartus_stp -t sdram_stream.tcl <hardware> <device> info
#        quartus_stp -t sdram_stream.tcl <hardware> <device> hold  <0|1>
#        quartus_stp -t sdram_stream.tcl <hardware> <device> crc   <word_address> <word_count>
#        quartus_stp -t sdram_stream.tcl <hardware> <device> streamwrite <word_address> <file>
#        quartus_stp -t sdram_stream.tcl <hardware> <device> streamread  <word_address> <word_count> <file>
#
# info prints INFO=<32-bit capability word in hex>; hold prints OK; crc prints CRC=<hex>; streamwrite
# writes the words of a text file (one hexadecimal word per line) and prints OK <count>; streamread writes
# the words read to the file, one hexadecimal word per line, and prints OK <count>.
package require ::quartus::jtag

if {[llength $argv] < 3} {
    puts stderr "Usage: quartus_stp -t sdram_stream.tcl <hardware> <device> info|hold|crc|streamwrite|streamread <args>"
    exit 1
}
lassign $argv HW DEV CMD
set ARGS [lrange $argv 3 end]

set INSTANCE 0
if {[info exists ::env(RV32_SDRAM_DEBUG_INSTANCE)]} {
    set INSTANCE $::env(RV32_SDRAM_DEBUG_INSTANCE)
}

# instructions of the Virtual JTAG node
set IR_DEBUG 1
set IR_STREAM_WRITE 2
set IR_STREAM_READ 3

# commands of the DEBUG register (op field) and the sub-commands of OP_CONTROL (be field)
set OP_STATUS 0
set OP_CONTROL 7
set SUB_INFO 0
set SUB_HOLD 1
set SUB_CRC_START 2
set SUB_CRC_READ 3
set SUB_SET_POINTER 4

set BUSY 1
set ERROR 2
set INITIALIZED 4
set DEADLINE_MS 3000
set CRC_DEADLINE_MS 120000

proc fail {code message} {
    puts stderr $message
    catch { device_unlock }
    catch { close_device }
    exit $code
}

proc select {ir} {
    global INSTANCE
    device_virtual_ir_shift -instance_index $INSTANCE -ir_value $ir -no_captured_ir_value
}

# one shift of the DEBUG register: returns {status word data} of the previous command
proc shift {op word data be} {
    global INSTANCE
    set op [expr {$op | ((($word >> 24) & 1) << 3)}]
    set v [expr {($op << 60) | ($be << 56) | (($word & 0xFFFFFF) << 32) | ($data & 0xFFFFFFFF)}]
    set r [device_virtual_dr_shift -instance_index $INSTANCE -length 64 \
               -dr_value [format %016llx $v] -value_in_hex]
    scan $r %llx x
    return [list [expr {($x >> 56) & 0xFF}] [expr {($x >> 32) & 0xFFFFFF}] [expr {$x & 0xFFFFFFFF}]]
}

proc settle {{deadline_ms 3000}} {
    global OP_STATUS BUSY ERROR
    set end [expr {[clock milliseconds] + $deadline_ms}]
    while {[clock milliseconds] < $end} {
        lassign [shift $OP_STATUS 0 0 0xF] status word data
        if {!($status & $BUSY)} {
            if {$status & $ERROR} { fail 4 "the SDRAM controller did not answer" }
            return [list $status $word $data]
        }
    }
    fail 5 "the debug command never finished"
}

# a control command: shifts it, waits for it and returns the data of its answer
proc control {sub word data {deadline_ms 3000}} {
    global OP_CONTROL
    shift $OP_CONTROL $word $data $sub
    lassign [settle $deadline_ms] status w d
    return $d
}

# the stream width, from the capability word (bits 15:8 are the words per shift)
proc stream_words {} {
    global SUB_INFO
    set info [control $SUB_INFO 0 0]
    set n [expr {($info >> 8) & 0xFF}]
    if {$n == 0} { fail 7 "this bitstream has no burst registers" }
    return $n
}

# the words of a text file, as a list
proc read_words {path} {
    if {[catch {open $path r} fh]} { fail 1 "cannot open $path: $fh" }
    set words {}
    while {[gets $fh line] >= 0} {
        set line [string trim $line]
        if {$line eq ""} { continue }
        if {[scan $line %x value] != 1} { fail 1 "not a hexadecimal word: $line" }
        lappend words $value
    }
    close $fh
    return $words
}

# the dr_value of a burst: word 0 in the lowest 32 bits, as a hexadecimal string of 8 digits per word
proc pack_hex {words} {
    set text ""
    foreach w [lreverse $words] { append text [format %08x $w] }
    return $text
}

if {[catch {
    open_device -hardware_name $HW -device_name $DEV
    device_lock -timeout 10000
    select $IR_DEBUG
} err]} {
    fail 2 "cannot open the debug port: $err"
}

lassign [settle $DEADLINE_MS] status word data
if {!($status & $INITIALIZED)} { fail 6 "the SDRAM is not initialized" }

switch $CMD {
    info {
        puts [format "INFO=%08x" [control $SUB_INFO 0 0]]
    }
    hold {
        lassign $ARGS value
        control $SUB_HOLD 0 [expr {$value ? 1 : 0}]
        puts "OK"
    }
    crc {
        lassign $ARGS first count
        control $SUB_CRC_START $first $count
        settle $CRC_DEADLINE_MS
        puts [format "CRC=%08x" [control $SUB_CRC_READ 0 0]]
    }
    streamwrite {
        lassign $ARGS first path
        set n [stream_words]
        set words [read_words $path]
        set total [llength $words]
        # the last burst is completed with the word it already holds: the host pads the file
        if {$total % $n} { fail 1 "the file has $total words, not a multiple of $n" }
        control $SUB_SET_POINTER $first 0
        for {set i 0} {$i < $total} {incr i $n} {
            select $IR_STREAM_WRITE
            device_virtual_dr_shift -instance_index $INSTANCE -length [expr {32 * $n}] \
                -dr_value [pack_hex [lrange $words $i [expr {$i + $n - 1}]]] -value_in_hex
            select $IR_DEBUG
            settle
        }
        puts "OK $total"
    }
    streamread {
        lassign $ARGS first count path
        set n [stream_words]
        if {$count % $n} { fail 1 "the count $count is not a multiple of $n" }
        control $SUB_SET_POINTER $first 0
        set out {}
        for {set i 0} {$i < $count} {incr i $n} {
            select $IR_STREAM_READ
            set r [device_virtual_dr_shift -instance_index $INSTANCE -length [expr {32 * $n}] \
                       -dr_value [string repeat 0 [expr {8 * $n}]] -value_in_hex]
            select $IR_DEBUG
            settle
            # word 0 is the lowest 32 bits, that is, the last 8 digits of the string
            for {set k 0} {$k < $n} {incr k} {
                set end [expr {[string length $r] - 8 * $k - 1}]
                lappend out [string range $r [expr {$end - 7}] $end]
            }
        }
        if {[catch {open $path w} fh]} { fail 1 "cannot write $path: $fh" }
        foreach w $out { puts $fh $w }
        close $fh
        puts "OK $count"
    }
    default { fail 1 "unknown command $CMD" }
}

device_unlock
close_device
exit 0
