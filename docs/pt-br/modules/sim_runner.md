# `sim_runner`

Dirige a simulação cocotb/GHDL, a contraparte de simulação do [`orchestrator`](orchestrator.md), que dirige o hardware real por JTAG. Não tem conhecimento específico de DUT: o `test_module` cocotb do próprio projeto (veja Configuração abaixo) conhece a hierarquia real de sinais VHDL e consulta o mailbox PASS/FAIL direto dos sinais simulados, a mesma convenção que o [`mailbox`](mailbox.md) usa no hardware real.

Precisa do extra opcional `sim` (`cocotb` + `cocotb-tools`, mais o GHDL no `PATH`); não é uma dependência obrigatória do pacote, então projetos que só usam o lado de hardware real não precisam instalá-lo.

## Configuração

| Chave | Significado |
| :--- | :--- |
| `sim.toplevel` | Entidade VHDL de topo que o GHDL elabora e à qual o cocotb se conecta. Sem padrão; específica do projeto. |
| `sim.vhdl_sources` | Fontes VHDL, em ordem de dependência (veja [`vhdl_sort`](vhdl_sort.md)). Sem padrão. |
| `sim.test_module` | O módulo de teste cocotb do próprio projeto. Sem padrão; é a peça que conhece os nomes de sinal do DUT e consulta o mailbox dele. |
| `sim.ghdl_std` | Padrão VHDL contra o qual o GHDL analisa (padrão `"08"`, VHDL-2008). |
| `sim.parameters` | Generics VHDL definidos no toplevel na etapa de execução do GHDL, por exemplo um modelo de ROM só de simulação que carrega a imagem por um generic em vez de uma variável de ambiente. Vazio por padrão. |
| `sim.image` | `hex` (padrão) ou `mif`: a imagem que a simulação carrega, veja Simulando com as memórias do hardware abaixo. |
| `sim.ghdl_flags` | Argumentos extras do GHDL, aplicados nas etapas de análise, elaboração e execução. Vazio por padrão. |
| `sim.libraries` | Bibliotecas VHDL analisadas uma vez antes das fontes, como `{biblioteca: [arquivos]}`. Vazio por padrão. |
| `sim.run_files` | Arquivos copiados para o diretório de execução de cada teste, como `{nome do arquivo: origem}`. Vazio por padrão. |
| `sim.env` | Variáveis de ambiente extras para o módulo de teste cocotb, como `{nome: modelo}`. Vazio por padrão. |

As quatro últimas usam modelos: `{hex_path}`, `{mif_path}`, `{boot_rom_hex_path}` e `{boot_rom_mif_path}` são substituídos por teste (veja [configuration.md](../configuration.md)).

## Simulando com as memórias do hardware

Por padrão a simulação carrega imagens `.hex` em modelos de memória feitos de arrays VHDL simples. Um projeto cujo topo de hardware instancia a IP de memória do fornecedor (o `altsyncram` do Quartus) pode ser simulado com essa IP, para que as memórias simuladas se comportem como as da FPGA. As peças são todas configuração:

1. `sim.image: mif`, para cada teste carregar o `.mif` que o `compile --emit mif` escreve e que o hardware carrega, e para o `.mif` da boot ROM também ser gerado.
2. `sim.libraries`, com a biblioteca do fornecedor (no Quartus, `altera_mf_components.vhd` e depois `altera_mf.vhd`, do diretório `eda/sim_lib` da instalação, por uma variável de ambiente para o caminho não ficar fixo) e `sim.ghdl_flags` com o que essa biblioteca exige (`-fsynopsys -fexplicit -frelaxed`). A biblioteca é analisada uma vez por execução do `sim`, em `<build_dir>/sim/sim_work/libraries`.
3. `sim.run_files`, porque a IP lê o conteúdo inicial de um nome de arquivo fixo no VHDL (por exemplo `init.mif`): cada entrada copia a imagem do teste, ou a da boot ROM, para esse nome no diretório de execução.
4. `sim.env`, para dizer a um módulo de teste escrito para outro topo (outros nomes de clock e reset, outro limite de tempo) o que dirigir.

O clock e o PLL não fazem parte disso: o modelo de simulação de um PLL em geral não é VHDL (o do Quartus é SystemVerilog, que o GHDL não roda), então o projeto fornece um substituto comportamental com as mesmas portas e parâmetros.

A chave `extends:` da configuração do projeto permite que isso seja um segundo arquivo curto ao lado do padrão, e o `--config` escolhe qual usar.

## Pré-requisitos

- O GHDL no `PATH`.
- O extra `sim` (`uv sync --extra sim`): `cocotb` e `cocotb-tools`.
- Com `sim.libraries`: as fontes da biblioteca de simulação do fornecedor.

## Testes

Os testes são pulados quando o GHDL ou o cocotb não estão disponíveis.

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_sim_runner.py::test_sim_runner_reports_pass` | Um DUT cujo teste passa é reportado como passou. |
| `tests/test_sim_runner.py::test_sim_runner_reports_fail` | Um DUT cujo teste falha é reportado como falhou. |
| `tests/test_sim_runner.py::test_sim_runner_parameters_reach_ghdl` | `sim.parameters` viram generics VHDL na etapa de execução do GHDL. |
| `tests/test_sim_runner.py::test_sim_runner_libraries_flags_run_files_and_env` | Uma biblioteca analisada à parte é encontrada, `sim.ghdl_flags` chegam a ela, `sim.run_files` caem no diretório de execução e `sim.env` chega ao módulo cocotb. |
| `tests/test_sim_runner.py::test_sim_runner_env_reaches_the_test_module` | Um valor esperado errado em `sim.env` faz o teste falhar, então o teste anterior prova que o valor chega. |
| `tests/test_sim_runner.py::test_build_libraries_needs_the_flags_the_library_needs` | Uma biblioteca que exige `-fsynopsys` não é analisada sem ele. |
| `tests/test_sim_runner.py::test_expand_env_replaces_variables` | `$VAR` e `${VAR}` num caminho são substituídos a partir do ambiente. |
| `tests/test_sim_runner.py::test_expand_env_rejects_an_unset_variable` | Uma variável não definida é um erro que a nomeia. |
| `tests/test_config_extends.py` | O `extends:` mescla por cima da base, substitui listas, é relativo ao arquivo que o declara, rejeita um laço e deixa uma configuração sem ele inalterada. |

## Uso

```bash
uv sync --extra sim
uv run riscv-tools --config /path/to/project/config.yaml compile --emit hex
uv run riscv-tools --config /path/to/project/config.yaml sim
```

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
