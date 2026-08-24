# Reads N contiguous words from a memory instance via JTAG.
#
# Usage: quartus_stp -t read_words.tcl <hardware> <device> <instance> <word_offset> <word_count>

package require ::quartus::insystem_memory_edit

if {[llength $argv] < 5} {
    puts stderr "Usage: quartus_stp -t read_words.tcl <hardware> <device> <instance> <word_offset> <word_count>"
    exit 1
}
lassign $argv HW DEV INSTANCE WORD_OFFSET WORD_COUNT

catch { end_memory_edit }
if {[catch { begin_memory_edit -hardware_name $HW -device_name $DEV } err]} {
    puts stderr "begin_memory_edit failed: $err"
    exit 2
}

if {[catch {
    set words [read_content_from_memory -instance_index $INSTANCE \
                   -start_address $WORD_OFFSET -word_count $WORD_COUNT]
} rerr]} {
    puts stderr "read_content_from_memory failed: $rerr"
    catch { end_memory_edit }
    exit 3
}

catch { end_memory_edit }
puts "WORDS=$words"
exit 0
