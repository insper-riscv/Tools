# Writes ONE word into a memory instance via JTAG, without touching
# the rest of that memory's content — unlike write_full.tcl
# (update_content_to_memory_from_file), which always overwrites the
# whole instance depth from a .mif. Used for single-word protocol
# words (e.g. a restart "go" flag) where wiping the rest of RAM would
# destroy data a running program has already written.
#
# Usage: quartus_stp -t write_word.tcl <hardware> <device> <instance> <word_offset> <value>

package require ::quartus::insystem_memory_edit

if {[llength $argv] < 5} {
    puts stderr "Usage: quartus_stp -t write_word.tcl <hardware> <device> <instance> <word_offset> <value>"
    exit 1
}
lassign $argv HW DEV INSTANCE WORD_OFFSET VALUE

catch { end_memory_edit }
if {[catch { begin_memory_edit -hardware_name $HW -device_name $DEV } err]} {
    puts stderr "begin_memory_edit failed: $err"
    exit 2
}

if {[catch {
    write_content_to_memory -instance_index $INSTANCE \
        -start_address $WORD_OFFSET -word_count 1 \
        -content [format %08x $VALUE] -content_in_hex
} werr]} {
    puts stderr "write_content_to_memory failed: $werr"
    catch { end_memory_edit }
    exit 3
}

catch { end_memory_edit }
puts "Wrote $VALUE to instance $INSTANCE word $WORD_OFFSET"
exit 0
