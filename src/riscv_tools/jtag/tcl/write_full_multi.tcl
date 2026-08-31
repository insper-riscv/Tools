# Writes the SAME .mif's content into multiple memory instances via
# JTAG, all inside ONE JTAG session (one begin_memory_edit/
# end_memory_edit pair) instead of one session per instance —
# write_full.tcl called N times pays N session open/close round-trips
# for what is, functionally, one logical write. Matters for a project
# that physically duplicates a memory across several instances that
# must always hold identical content (see rom_writer.write_rom's
# docstring for why RV32IM needs this: ENABLE_RUNTIME_MOD doesn't
# support a true DUAL_PORT memory in this Quartus edition, so it uses
# two separate single-port ROM copies instead — each JTAG session has
# real overhead, and this project's tests already stack up a lot of
# JTAG traffic per run).
#
# Usage: quartus_stp -t write_full_multi.tcl <hardware> <device> <mif_path> <instance>...

package require ::quartus::insystem_memory_edit

if {[llength $argv] < 4} {
    puts stderr "Usage: quartus_stp -t write_full_multi.tcl <hardware> <device> <mif_path> <instance>..."
    exit 1
}
set HW [lindex $argv 0]
set DEV [lindex $argv 1]
set MIF_PATH [lindex $argv 2]
set INSTANCES [lrange $argv 3 end]

catch { end_memory_edit }
if {[catch { begin_memory_edit -hardware_name $HW -device_name $DEV } err]} {
    puts stderr "begin_memory_edit failed: $err"
    exit 2
}

foreach INSTANCE $INSTANCES {
    if {[catch {
        update_content_to_memory_from_file -instance_index $INSTANCE \
            -mem_file_path $MIF_PATH -mem_file_type "mif"
    } uerr]} {
        puts stderr "update_content_to_memory_from_file failed for instance $INSTANCE: $uerr"
        catch { end_memory_edit }
        exit 3
    }
    puts "Wrote $MIF_PATH to instance $INSTANCE"
}

catch { end_memory_edit }
exit 0
