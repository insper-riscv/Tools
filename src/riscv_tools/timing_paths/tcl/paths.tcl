# Lists the worst setup paths of every clock domain of a compiled Quartus project.
#
# Usage: quartus_sta -t paths.tcl <project> <paths per clock> <slow|fast>
#
# Prints one line per path, tab separated, after the marker PATH:
#   PATH <destination clock> <slack ns> <data delay ns> <source node> <destination node>
# The clocks without a setup path print nothing.
if {[llength $argv] < 3} {
    puts stderr "Usage: quartus_sta -t paths.tcl <project> <paths per clock> <slow|fast>"
    exit 1
}
lassign $argv PROJECT NPATHS MODEL

project_open $PROJECT
create_timing_netlist -model $MODEL
read_sdc
update_timing_netlist

foreach_in_collection clk [get_clocks *] {
    set name [get_clock_info -name $clk]
    set paths [get_timing_paths -setup -npaths $NPATHS -to_clock $clk]
    foreach_in_collection p $paths {
        puts [format "PATH\t%s\t%s\t%s\t%s\t%s" $name \
            [get_path_info $p -slack] [get_path_info $p -data_delay] \
            [get_node_info -name [get_path_info $p -from]] \
            [get_node_info -name [get_path_info $p -to]]]
    }
}

delete_timing_netlist
project_close
