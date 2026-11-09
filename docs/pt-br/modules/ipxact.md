# `ipxact`

Gera e confere as descrições IP-XACT ([IEEE Std 1685-2022](https://standards.ieee.org/ieee/1685/10199/)) dos blocos VHDL de um repositório. O VHDL é a fonte da verdade, e os arquivos XML são gerados, versionados e conferidos pela CI, nunca editados à mão.

## 1. Comandos

| Comando | O que faz |
| :--- | :--- |
| `riscv-tools --root <repositório> ipxact extract` | Imprime os generics e as portas de cada entidade, lidos do VHDL |
| `riscv-tools --root <repositório> ipxact generate` | Escreve `ipxact/<nome>.<versão>.component.xml` para cada entidade e valida o que escreveu |
| `riscv-tools --root <repositório> ipxact generate --check` | Não escreve; falha quando um documento versionado difere do que o VHDL gera |
| `riscv-tools --root <repositório> ipxact check` | Falha quando falta um documento, sobra um, algum difere do VHDL ou o padrão rejeita algum |

Nenhum deles precisa de `--config`. O `generate` e o `check` saem com status 1 diante de qualquer problema e com status 2 quando o repositório não tem manifesto `provides`.

## 2. Extração do VHDL

As fontes seguem a ordem do manifesto `provides` (ver [sources](sources.md)). Para cada componente do manifesto, o módulo analisa o fecho de dependências com `ghdl -a --std=08 -Werror` numa biblioteca temporária e exporta a árvore sintática com `ghdl --file-to-xml`. Dessa árvore saem as entidades dos arquivos do componente.

| Elemento do VHDL | Elemento IP-XACT |
| :--- | :--- |
| Generic `natural`, `positive`, `integer` | `ipxact:parameter` do tipo `int`, com `minimum` e `maximum` do subtipo |
| Generic `boolean` | `ipxact:parameter` do tipo `bit`, com valor `0` ou `1` |
| Generic `std_logic` ou `std_logic_vector` | `ipxact:parameter` do tipo `bit`, com valor dimensionado (`8'hA5`) |
| Generic `string` | `ipxact:parameter` do tipo `string` |
| Porta `std_logic`, `std_logic_vector`, `unsigned`, `signed`, `bit`, `bit_vector` | `ipxact:port` com `ipxact:wire`, direção e `wireTypeDef` |
| Porta de um tipo matriz de vetores declarado num pacote | `ipxact:wire` com um `ipxact:vector` por dimensão |
| Limites de vetor e padrões | Expressões em SystemVerilog dos generics (`(width - 1)`) |

O comentário logo acima de cada generic e porta vira o `ipxact:description`, e a primeira linha de texto do cabeçalho do arquivo vira a descrição do componente.

### 2.1. Expressões

O IP-XACT só aceita identificadores de parâmetros em uma expressão (SCR 5.18), então o módulo escreve cada limite com os generics como identificadores. Uma constante de pacote é trocada pelo valor, e uma chamada de função é tratada assim.

| Chamada no VHDL | Resultado |
| :--- | :--- |
| `pick(c, a, b)` | `(c ? a : b)`, ou o valor escolhido quando `c` é constante |
| `log2_ceil(x)` e `log2_exact(x)` | `$clog2(x)` (cláusula E.5.1) |
| Função cujo corpo é uma sequência de `return` e de `if` sem `else` | O corpo expandido, com os argumentos no lugar dos parâmetros |
| Outra função | Recusada, com a linha do VHDL |

Um construto sem forma em IP-XACT (porta de tipo inteiro, limite dado por atributo) não vira documento a menos que a entidade esteja em `ipxact.exceptions` do `paths.yaml`, com a justificativa. O `check` falha quando uma exceção cobre uma entidade que se traduz ou nenhuma entidade.

### 2.2. Bibliotecas de fornecedor

Um arquivo que cita uma biblioteca fora de `ieee`, `std` e `work` (como `altera_mf`, que vem com o Quartus) é analisado só com a declaração da entidade: as linhas que citam a biblioteca viram comentário e o que vem depois do fim da entidade é esvaziado, sem mudar a numeração das linhas.

## 3. O documento gerado

| Parte | Conteúdo |
| :--- | :--- |
| VLNV | Vendor `insper.edu.br`, biblioteca do repositório (`common`, `core`, `memory`, `peripherals`, `top`), nome da entidade e versão do `pyproject.toml` do repositório |
| `ipxact:model` | Visão `rtl` (`VHDL:*:*`), instanciação `rtl_instantiation` com `moduleParameters` ligados aos parâmetros, e as portas |
| `ipxact:fileSets` | Conjunto `rtl_sources` com os arquivos do componente do manifesto, tipo `vhdlSource-2008` |
| `ipxact:parameters` | Um parâmetro `user` por generic, com o padrão do VHDL |
| `ipxact:vendorExtensions` | O componente do manifesto e seus `requires` (namespace do projeto) |

O nome do arquivo é `<nome>.<versão>.component.xml`, e dois componentes do mesmo repositório com a mesma entidade são um erro.

## 4. Validação

A validação roda sem rede.

| Camada | O que confere |
| :--- | :--- |
| Esquema | Os XSD do IEEE 1685-2022 publicados pela Accellera (Apache 2.0), empacotados sem alteração em `src/riscv_tools/ipxact/schemas/1685-2022/` com o NOTICE, lidos pelo `xmlschema` |
| Regras semânticas | As regras da tabela abaixo, que o esquema não expressa |
| Consistência com o VHDL | O documento versionado é igual ao que o VHDL gera (`generate --check`) |

| Regra | Cláusula | O que confere |
| :--- | :--- | :--- |
| SCR 1.10 | B.2.1 | O elemento do documento é um tipo legal |
| SCR 5.2 | C.6.2 | `parameterId` em parâmetro `user` ou `generated` |
| SCR 5.13 | C.7 | Valor dentro de `minimum` e `maximum` |
| SCR 5.14 | 6.15.2.2 | Parâmetro de módulo só vale dentro da sua instanciação |
| SCR 5.16 | C.21 | Valor resolve para o tipo do parâmetro |
| SCR 5.17 | Anexo E | Expressão bem formada |
| SCR 5.18 | C.9.2 | Todo identificador de expressão é um `parameterId` |
| SCR 5.19 | B.2.5 | Expressão sem referência circular |
| SCR 6.26 | 6.15.1.2 | Componente sem visões só tem portas `phantom` |
| C.29.2 | C.29 | `viewRef` aponta para uma visão e cada visão aparece uma vez por `wireTypeDefs` |
| C.7.11 | C.7.11 | Limite de vetor é um inteiro não negativo |

A unicidade do VLNV (SCR 1.1) vem do nome do arquivo, e a existência dos documentos referenciados (SCR 1.2) não se aplica a um componente que não referencia outros.

## 5. Dados escritos por pessoas no `paths.yaml`

```yaml
ipxact:
  exceptions:
    uart_fifo: a porta o_level é um inteiro, sem forma em IP-XACT

interfaces:
  generic_register:
    buses:
      - name: clock
        contract: clock
        role: target
        ports: {prefix: i_clk}
    unbound:
      i_enable: habilitação sem contrato de barramento
```

| Chave | Conteúdo |
| :--- | :--- |
| `ipxact.exceptions` | Entidade (ou componente do manifesto) sem documento, com o motivo |
| `interfaces.<entidade>.buses` | Interfaces de barramento: `name` único, `contract`, `role` (`initiator`, `target`, `system`, `mirroredInitiator`, `mirroredTarget`, `mirroredSystem`, `monitor`) e `ports` por `prefix` ou `names` |
| `interfaces.<entidade>.unbound` | Portas fora de qualquer interface, com a justificativa |

A regra `manifest` do `check-tree` confere a forma das duas seções.

## 6. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_ipxact_sv_expr.py` | O avaliador de expressões segue a precedência do SystemVerilog e recusa as malformadas |
| `tests/test_ipxact_flow.py` | Extração de generics e portas, expansão de funções, biblioteca de fornecedor, geração, `--check`, exceções e a linha de comando |
| `tests/test_ipxact_semantic.py` | Cada regra semântica falha com o seu número quando quebrada |
| `tests/test_ipxact_manifest.py` | As seções do `paths.yaml`, a regra `manifest` do `check-tree` e o recorte de biblioteca de fornecedor |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
