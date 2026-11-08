#!/usr/bin/env bash
# Programa a DE0-CV pelo cabo USB-Blaster com o .sof compilado por de0-cv_synth.tcl.
#
#   src/cyclone-v/de0-cv/de0-cv_program.sh [arquivo.sof]
#
# Sem argumento usa output_files/de0-cv.sof. O cabo é o primeiro que o jtagconfig lista; a variável
# CABLE o substitui (por exemplo CABLE="USB-Blaster [1-4]") quando há mais de uma placa conectada.
# Depois de compilar, rode este script no mesmo shell da compilação (cmd1 && cmd2).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
sof="${1:-output_files/de0-cv.sof}"

if [ ! -f "$sof" ]; then
  echo "erro: $sof não existe, compile antes com de0-cv_synth.tcl" >&2
  exit 1
fi

cable="${CABLE:-$(jtagconfig | sed -n 's/^1) //p' | head -n 1)}"
if [ -z "$cable" ]; then
  echo "erro: o jtagconfig não encontrou nenhum cabo" >&2
  exit 1
fi

exec quartus_pgm -c "$cable" -m JTAG -o "p;$sof"
