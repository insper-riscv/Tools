# Lists the editable memory instances of the programmed board: the index,
# the depth, the width, the access mode, the type and the name of each.
#
# Usage: quartus_stp -t list_mems.tcl <hardware> <device>
#
# Prints one line MEM <index> <depth> <width> <mode> <type> <name> per
# instance (the name is the INSTANCE_NAME of the IP, which the editor may
# cut to its first four characters; it is empty for an unnamed instance)
# and, last, COUNT=<how many instances there are>.

package require ::quartus::insystem_memory_edit

if {[llength $argv] < 2} {
    puts stderr "Usage: quartus_stp -t list_mems.tcl <hardware> <device>"
    exit 1
}
lassign $argv HW DEV

catch { end_memory_edit }
if {[catch { begin_memory_edit -hardware_name $HW -device_name $DEV } err]} {
    puts stderr "begin_memory_edit failed: $err"
    exit 2
}

if {[catch {
    set instances [get_editable_mem_instances -hardware_name $HW -device_name $DEV]
} lerr]} {
    puts stderr "get_editable_mem_instances failed: $lerr"
    catch { end_memory_edit }
    exit 3
}

foreach inst $instances {
    puts "MEM [lindex $inst 0] [lindex $inst 1] [lindex $inst 2] [lindex $inst 3] [lindex $inst 4] [lindex $inst 5]"
}
catch { end_memory_edit }
puts "COUNT=[llength $instances]"
exit 0
