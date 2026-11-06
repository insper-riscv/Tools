# Compila um projeto do Quartus com modo de otimização e semente fixos, para o resultado ser reproduzível.
# Substitui os <projeto>_synth.tcl de cada plataforma. Rode pelo Quartus, na pasta do projeto:
#
#   quartus_sh -t compile.tcl <projeto> <semente> <até> [GENERIC=valor ...]
#
# <até> é map, fit, sta ou full. Com map só a síntese roda, com fit síntese e ajuste, com sta também a análise de tempo e com
# full o fluxo inteiro (que gera o .sof). Cada GENERIC=valor troca um generic do topo só nesta compilação, sem gravá-lo
# no .qsf versionado.

load_package flow

if {$argc < 3} {
    puts "Erro: uso: compile.tcl <projeto> <semente> <map|fit|sta|full> \[GENERIC=valor ...\]"
    exit 2
}

set project [lindex $quartus(args) 0]
set seed [lindex $quartus(args) 1]
set stop [lindex $quartus(args) 2]
set generics {}
foreach arg [lrange $quartus(args) 3 end] {
    if {[regexp {^([A-Za-z_][A-Za-z0-9_]*)=([0-9]+)$} $arg -> name value]} {
        lappend generics $name $value
    } else {
        puts "Erro: argumento desconhecido '$arg'."
        exit 2
    }
}
if {![string is integer -strict $seed] || $seed < 1} {
    puts "Erro: a semente deve ser um inteiro positivo, recebi '$seed'."
    exit 2
}
if {[lsearch -exact {map fit sta full} $stop] < 0} {
    puts "Erro: o ponto de parada deve ser map, fit, sta ou full, recebi '$stop'."
    exit 2
}

project_open $project
set_global_assignment -name OPTIMIZATION_MODE "HIGH PERFORMANCE EFFORT"
set_global_assignment -name SEED $seed
foreach {name value} $generics {
    set_parameter -name $name $value
}

if {[string equal $stop full]} {
    execute_flow -compile
} else {
    execute_module -tool map
    if {[lsearch -exact {fit sta} $stop] >= 0} {
        execute_module -tool fit
    }
    if {[string equal $stop sta]} {
        execute_module -tool sta
    }
}

project_close -dont_export_assignments
