# HTIF: `tohost` e `fromhost`

## 1. O que é

O HTIF (Host-Target InterFace) é a convenção pela qual um programa em execução num núcleo RISC-V conversa com o computador hospedeiro por duas palavras de memória, sem periférico nenhum. Ele não faz parte da especificação da ISA nem da arquitetura privilegiada: nasceu no front-end server (`fesvr`) do Spike, o simulador de referência mantido em [riscv-software-src/riscv-isa-sim](https://github.com/riscv-software-src/riscv-isa-sim), e virou o jeito padrão de um teste dizer que terminou. O `riscv-tests` e o `riscv-arch-test` (ACT4) terminam assim, e é por isso que o mesmo programa roda no Spike, na simulação e na placa.

## 2. Os dois símbolos

| Símbolo | Quem escreve | Para que serve |
| :--- | :--- | :--- |
| `tohost` | o programa | enviar um comando ao hospedeiro, em particular o resultado final do teste |
| `fromhost` | o hospedeiro | devolver uma resposta ao programa |

Cada um é uma palavra de 64 bits, em little-endian. Num núcleo RV32 o programa escreve duas palavras de 32 bits, a baixa no endereço do símbolo e a alta 4 bytes acima. O Spike não recebe os endereços por parâmetro: ele os procura na tabela de símbolos do ELF, pelos nomes `tohost` e `fromhost`. Sem o símbolo `tohost`, nenhuma comunicação acontece.

Neste projeto os dois ficam lado a lado, com o `fromhost` 8 bytes acima do `tohost` (`memory.tohost_addr` e `memory.fromhost_addr` no `config.yaml`).

## 3. Formato de um comando em `tohost`

O hospedeiro lê o `tohost` como um comando de 64 bits dividido em três campos.

| Bits | Campo | Significado |
| :--- | :--- | :--- |
| 63 a 56 | `device` | qual dispositivo do hospedeiro trata o comando |
| 55 a 48 | `cmd` | qual operação desse dispositivo |
| 47 a 0 | `payload` | o argumento da operação |

O dispositivo 0 é o proxy de chamadas de sistema, e o 1 é o console de caracteres. Quando o `device` e o `cmd` são zero, o `payload` tem dois significados, escolhidos pelo bit 0.

| Bit 0 do `payload` | Significado |
| :--- | :--- |
| `1` | fim do programa; o código de saída é `payload >> 1` |
| `0` | endereço de um bloco de oito palavras na memória do alvo: o número da chamada de sistema e sete argumentos, que o hospedeiro executa e responde no mesmo bloco |

## 4. Terminar um teste

Um teste termina escrevendo um `payload` com o bit 0 em `1` no `tohost`.

| Resultado | Valor escrito | Código de saída |
| :--- | :--- | :--- |
| passou | `1` | 0 |
| falhou | `(código << 1) \| 1`, com `código` diferente de zero | `código` |

O `código` costuma ser o número da checagem que falhou, o que torna uma falha rastreável sem depurador. Enquanto o teste roda, o `tohost` vale 0.

O Spike consulta o `tohost` o tempo todo. Ao ler um valor diferente de zero, ele o apaga, para indicar que recebeu, e trata o comando. Num fim de programa, o Spike termina com o código de saída do teste, passando ou falhando.

## 5. O `fromhost`

Quando o hospedeiro tem uma resposta, ele a escreve no `fromhost`, mas só depois que o programa apagou a resposta anterior (leu e escreveu 0). É esse controle de fluxo que impede uma resposta de sobrescrever outra ainda não lida. Um teste que só termina, como os deste projeto, nunca precisa ler o `fromhost` para isso.

## 6. Como este projeto usa o HTIF

| Contexto | `tohost` | `fromhost` |
| :--- | :--- | :--- |
| Spike (gerar golden, `spike-run`) | o Spike lê e termina com o código do teste, como na seção 4 | resposta padrão do Spike |
| Simulação (cocotb/GHDL) | o teste cocotb observa os sinais da escrita no `tohost` | não usado |
| Placa | o hospedeiro lê a palavra baixa por JTAG até o bit 0 ficar em `1` | o hospedeiro escreve um valor diferente de zero para reiniciar o núcleo |

Dois pontos diferem do Spike.

1. **Leitura por JTAG.** Na placa não existe um `fesvr` para decodificar o comando. O hospedeiro lê só a palavra baixa do `tohost` e considera o teste terminado quando o bit 0 vale `1`. Um `1` é aprovado, e `(código << 1) | 1` é falha com o `código` mostrado pelo `run` (`FAIL (code N)`).
2. **`fromhost` como reinício.** Depois de carregar a ROM do próximo teste, o hospedeiro escreve um valor diferente de zero no `fromhost`. O código de boot do projeto fica esperando esse valor e então volta ao ponto de entrada, o que permite rodar vários testes no mesmo bitstream sem reprogramar a placa.

Antes de cada teste o hospedeiro zera as duas palavras do `tohost`, porque o resultado do teste anterior ainda está lá. Sem isso, o hospedeiro leria um valor antigo e declararia o teste novo aprovado antes de ele rodar.

Do lado do programa, o `rv32_test.h` gerado por `riscv-tools generate-header` traz o `RV32_PASS()` e o `RV32_FAIL(código)` (veja [creating-a-c-test.md](creating-a-c-test.md)), além dos nomes `RVMODEL_HALT_PASS` e `RVMODEL_HALT_FAIL(código)` que o ACT4 espera. Para um teste em assembly, veja [creating-an-asm-test.md](creating-an-asm-test.md). O módulo que lê e reinicia pela placa é descrito em [htif](modules/htif.md).

## 7. Referências

- [riscv-software-src/riscv-isa-sim](https://github.com/riscv-software-src/riscv-isa-sim), diretório `fesvr`: a implementação de referência do lado do hospedeiro.
- [riscv-software-src/riscv-tests](https://github.com/riscv-software-src/riscv-tests): os testes que terminam escrevendo o `tohost`.
- [riscv-non-isa/riscv-arch-test](https://github.com/riscv-non-isa/riscv-arch-test): a suíte de certificação (ACT4) que este projeto também usa.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../LICENSE).
