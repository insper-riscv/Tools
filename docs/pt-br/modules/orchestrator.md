# `orchestrator`

Compõe todos os outros módulos de hardware real numa rodada completa de testes, ou num sweep de frequência de clock para achar a Fmax. É a contraparte em hardware real do [`sim_runner`](sim_runner.md), que dirige o mesmo tipo de execução contra a simulação cocotb/GHDL em vez de uma placa física.

## Rodando uma suíte

Para cada teste de um manifest: recarrega a imagem de ROM dele por JTAG (veja [`rom_writer`](rom_writer.md)), dá um pulso na flag de reinício (veja [`mailbox`](mailbox.md)), espera o mailbox PASS/FAIL e, nos testes do tipo `memory`, faz o dump da RAM e a valida (veja [`ram_dump`](ram_dump.md), [`mem_validator`](mem_validator.md)).

Se o mailbox de um teste nunca responde, três níveis de recuperação rodam em ordem, cada um só tentado se o anterior não resolveu:

1. **Nova tentativa de recarga por JTAG**: tenta a mesma recarga de ROM mais uma vez, caso a tentativa anterior tenha sido um problema isolado.
2. **Reprogramar a partir do `.sof` existente**: barato (~10s), seguro só se o fonte VHDL não mudou desde que esse `.sof` foi gerado (veja o `program_only` do [`quartus_program`](quartus_program.md)).
3. **Recompilação completa + reprogramação**: o caminho lento, só tentado se o nível 2 falhou especificamente porque o `.sof` ainda não existe, e não porque a placa simplesmente estava inacessível. Uma recompilação completa gera o mesmo bitstream que o nível 2 já tentou, então repeti-la quando o problema é a própria placa gasta minutos sem recuperar nada.

## Quando nenhuma nova tentativa automática ajuda

Uma falha cujo próprio texto de erro combina com uma assinatura conhecida de hardware/cabo (por exemplo `"can't scan jtag chain"`, `"jtag chain broken"`, `"hardware is not found"`) levanta `NeedsHumanInterventionError` imediatamente, pulando os níveis restantes: nenhum deles conserta uma chain JTAG fisicamente caída, e passar por recompilações de ~4-5 minutos cada, nessa situação, já se observou não recuperar nada.

Por padrão, isso interrompe a suíte e retorna, salvando o progresso para que uma nova execução simples depois retome do passo que falhou em vez de repetir os testes já concluídos. Passar `wait_for_hardware=True` faz, em vez disso, imprimir a mesma mensagem e consultar o `jtag.jtag_chain_healthy` (veja [`jtag`](jtag.md)) a cada poucos segundos até a chain se recuperar sozinha, por exemplo depois de alguém desligar e ligar fisicamente a placa, e então retomar automaticamente sem uma nova invocação separada. Pensado para uma sessão interativa que alguém está acompanhando; o CI mantém o comportamento padrão de parar e sair, já que nada ali conseguiria desligar e ligar uma placa por conta própria.

## Sweep de frequência

Acha a maior frequência de clock (Fmax) em que um design ainda passa na sua suíte de testes, reescrevendo o PLL (veja [`freq_sweep`](freq_sweep.md)) e fazendo uma recompilação + reprogramação + comparação completas em cada frequência candidata. Passo a passo completo: [docs/finding-fmax.md](../finding-fmax.md).

## Configuração

| Chave | Significado |
| :--- | :--- |
| `quartus.program_wait_seconds` | Quanto esperar após uma reconfiguração completa (só no caminho de fallback) antes de ler o mailbox (padrão `15`). |
| `quartus.default_timeout_s` | Timeout padrão por teste se o teste não define o próprio cabeçalho `RV32_TIMEOUT_S` (padrão `15`; veja [`compiler`](compiler.md)). |

## Pré-requisitos

- O Quartus Prime Lite no `PATH` (`quartus_stp`, `quartus_sh`, `quartus_pgm`, `jtagconfig`), instalado como no `QUARTUS_INSTALL.md` do Infra, e uma placa com um USB-Blaster conectado por JTAG.
- A toolchain GCC RISC-V (`riscv32-unknown-elf-gcc`, `-objcopy`, `-nm`) no `PATH`, instalada como no `GCC_SETUP.md` do [insper-riscv/Infra](https://github.com/insper-riscv/Infra), para o build da boot ROM.

## Testes

Não há teste automatizado neste repositório. Um runner self-hosted preparado como no `RUNNER_SETUP.md` do Infra roda a suíte de hardware real de um projeto consumidor (`riscv-tools run`), que é o único lugar onde este módulo é exercitado.

## Uso

```bash
uv run riscv-tools --config /path/to/project/config.yaml run
uv run riscv-tools --config /path/to/project/config.yaml run --wait-for-hardware
uv run riscv-tools --config /path/to/project/config.yaml run --only test-a,test-b
uv run riscv-tools --config /path/to/project/config.yaml freq-sweep \
    build/real/full.mif --golden golden/full.json --start 1 --stop 30 --step 2
```

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
