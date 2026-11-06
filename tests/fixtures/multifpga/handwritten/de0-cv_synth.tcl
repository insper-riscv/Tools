# Compila o projeto de0-cv em linha de comando, com modo de otimização e semente fixos para o resultado
# ser reproduzível. Rode de qualquer pasta, pelo Quartus:
#
#   quartus_sh -t src/cyclone-v/de0-cv/de0-cv_synth.tcl [semente] [map] [GENERIC=valor ...]
#
# O primeiro argumento é a semente do posicionamento (padrão 5). Com `map` no segundo argumento só a
# síntese roda (quartus_map), que basta para conferir que os caminhos e as entidades resolvem. Cada
# argumento `GENERIC=valor` troca um generic do topo só nesta compilação (por exemplo `HPM_COUNTERS=4
# HPM_WIDTH=40` para o núcleo reduzido do Zihpm). As atribuições feitas aqui não são gravadas no .qsf versionado.
#
# Para programar a placa logo depois, encadeie o programador no MESMO shell (um quartus_pgm em outro
# processo-pai falha com "Can't scan JTAG chain"):
#
#   quartus_sh -t src/cyclone-v/de0-cv/de0-cv_synth.tcl && src/cyclone-v/de0-cv/de0-cv_program.sh

load_package flow

set project "de0-cv"
set seed 5
set only_map 0

if {$argc >= 1} {
    set seed [lindex $quartus(args) 0]
}
if {$argc >= 2} {
    set only_map [string equal [lindex $quartus(args) 1] "map"]
}
set generics {}
foreach arg [lrange $quartus(args) 1 end] {
    if {[regexp {^([A-Za-z_][A-Za-z0-9_]*)=([0-9]+)$} $arg -> name value]} {
        lappend generics $name $value
    } elseif {![string equal $arg "map"]} {
        puts "Erro: argumento desconhecido '$arg'."
        exit 2
    }
}
if {![string is integer -strict $seed] || $seed < 1} {
    puts "Erro: a semente deve ser um inteiro positivo, recebi '$seed'."
    exit 2
}

cd [file dirname [file normalize [info script]]]

project_open $project
set_global_assignment -name OPTIMIZATION_MODE "HIGH PERFORMANCE EFFORT"
set_global_assignment -name SEED $seed
foreach {name value} $generics {
    set_parameter -name $name $value
}

if {$only_map} {
    execute_module -tool map
} else {
    execute_flow -compile
}

project_close -dont_export_assignments
