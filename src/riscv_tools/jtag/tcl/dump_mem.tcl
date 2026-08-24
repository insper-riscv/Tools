# Dumps a memory instance's full content to a .mif via JTAG — used
# for RV32_TEST_KIND: memory tests that need more than a single
# PASS/FAIL word checked.
#
# Usage: quartus_stp -t dump_mem.tcl <hardware> <device> <instance> <out.mif>

package require ::quartus::insystem_memory_edit

if {[llength $argv] < 4} {
    puts stderr "Usage: quartus_stp -t dump_mem.tcl <hardware> <device> <instance> <out.mif>"
    exit 1
}
lassign $argv HW DEV INSTANCE OUTFILE

catch { end_memory_edit }
if {[catch { begin_memory_edit -hardware_name $HW -device_name $DEV } err]} {
    puts stderr "begin_memory_edit failed: $err"
    exit 2
}

if {[catch {
    save_content_from_memory_to_file -instance_index $INSTANCE \
        -mem_file_path $OUTFILE -mem_file_type "mif"
} serr]} {
    puts stderr "save_content_from_memory_to_file failed: $serr"
    catch { end_memory_edit }
    exit 3
}

catch { end_memory_edit }
puts "Dumped instance $INSTANCE to $OUTFILE"
exit 0
