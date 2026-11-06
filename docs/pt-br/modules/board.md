# `board`

Descobre qual placa está ligada ao host, escolhe a placa certa para uma plataforma, a trava para uso exclusivo e diz qual cabo usar. A leitura do `jtagconfig` é a do módulo [`jtag`](jtag.md) (`read_cables`); este módulo só interpreta o que ela devolve.

## 1. Referência

O plano de identificação pelo JTAG (`Plans/Multi-FPGA/03-IDENTIFICACAO-PELO-JTAG.md`) define o algoritmo, os nove casos de ambiguidade e a trava por placa. As placas conhecidas vêm dos pacotes `<pasta>/<placa>/board.yaml` do Insper-RISC-V, dos quais só a parte `jtag` é lida.

```yaml
board: de0-cv
device: 5CEBA4F23C7
jtag:
  cable: usb-blaster      # usb-blaster-ii, samd21-usbblaster, external
  chain: [{name: "5CE(BA4|FA4)", idcode: "02B050DD", fpga: true}]
```

## 2. O que identifica uma placa

A placa é o par (IDCODE da cadeia, caminho estável da porta USB). O IDCODE diz o que a placa pode ser, e a porta diz qual das candidatas é.

| Fonte | Uso |
| :--- | :--- |
| IDCODE sem os 4 bits de versão | Candidatas da cadeia; o `031050DD` não separa `10M50DA` de `10M50DC`, e o módulo avisa |
| `ID_PATH` do udev da porta (`pci-0000:00:14.0-usb-0:2`) | Chave de desambiguação; sem `udevadm`, vale a posição em `/sys/devices` com o prefixo `sys:` |
| Nome do cabo (`USB-Blaster [1-2]`) | Só o argumento `-c` da sessão, nunca chave |
| Número de série USB | Descartado, porque o mesmo valor aparece em vários cabos |

A cadeia de uma candidata deve conter os IDCODEs do `board.yaml`, na ordem. O cabo `DE-SoC` e o `USB-BlasterII` são do tipo `usb-blaster-ii`, e os demais são `usb-blaster`.

## 3. Inventário do host

O inventário liga a porta USB a uma placa. É lido de `~/.config/riscv-tools/boards.yaml`, ou de `/etc/riscv-tools/boards.yaml`, e o primeiro que existe vale.

```yaml
host: ws
lock_dir: /tmp
boards:
- {id: de0-cv-ws, board: de0-cv, usb_path: "pci-0000:00:14.0-usb-0:2"}
- {id: de2-115-ws, board: de2-115, usb_path: "pci-0000:00:14.0-usb-0:3"}
```

Sem o arquivo, uma placa com uma só candidata ainda é identificada, e o `host` é o nome curto da máquina ou o valor de `RISCV_TOOLS_HOST`. O comando `board scan --save` grava os cabos certos; um cabo com várias candidatas pede `--assign PORTA=PLACA`.

## 4. Subcomandos

| Comando | Efeito |
| :--- | :--- |
| `board scan [--save] [--assign PORTA=PLACA] [--json]` | Lista cada cabo com cadeia, porta, placas possíveis e entrada do inventário |
| `board select [--cable C] [--board-id I] [--board B] [--platform platform.yaml] [--free] [--all] [--json]` | Escolhe a placa e o cabo; `--all` lista todas as presentes |
| `board lock <opções de select> [--wait [S]] (-- comando \| --hold)` | Escolhe, trava e roda o comando sob a trava, ou segura a trava até a entrada padrão fechar |
| `board doctor [--json]` | Verifica cabo, cadeia, processos e as placas especiais, sem alterar nada |

As opções de local são `--boards-dir` (repetível, além de `RISCV_TOOLS_BOARDS` e de `<raiz>/Insper-RISC-V/boards`), `--inventory`, `--host` e `--idcode`. O `--idcode` serve a uma placa sem pacote, que passa a se chamar `adhoc`.

A saída de `select` traz `board`, `id`, `cable`, `device` (a identidade `@N: nome (0xIDCODE)` do FPGA na cadeia, no formato de `quartus.jtag_device`), `idcode`, `port`, `lock_file`, `warnings` e `free`. O código de saída é 2 para erro de seleção, com o número do caso, e 3 quando todas as placas estão ocupadas.

## 5. Precedência da seleção

Da fonte mais forte para a mais fraca vale `--cable`, `--board-id`, `--board`, o `board:` do `platform.yaml` e `auto`. Os mesmos três primeiros existem como opções globais (`riscv-tools --board X run`) e como variáveis `RISCV_TOOLS_CABLE`, `RISCV_TOOLS_BOARD_ID` e `RISCV_TOOLS_BOARD`.

| Fonte | Efeito |
| :--- | :--- |
| `--cable` | Força o cabo e dispensa o inventário; a cadeia ainda é conferida contra a placa esperada |
| `--board-id` | Escolhe a entrada do inventário e confere o cabo da porta dela |
| `--board` ou `board: <nome>` | Fixa a placa e escolhe entre os cabos que a apresentam |
| `board: auto` | Escolhe entre as placas de `boards:` presentes e livres |

Duas candidatas iguais sem desempate são um erro de caso 2 com a lista dos cabos. A opção `--free` escolhe, entre as iguais, a primeira livre na ordem das portas, e nunca a ordem de listagem do `jtagconfig`.

## 6. Os nove casos

| # | Caso | Resultado |
| :--- | :--- | :--- |
| 1 | Um cabo, uma candidata | Escolhida |
| 2 | Duas placas iguais no mesmo host | Erro com a lista de cabos, ou o inventário (ou `--free`) desempata |
| 3 | Placas iguais em hosts diferentes | Cada host tem o seu inventário e o `id` leva o nome do host |
| 4 | Mesmo IDCODE de dispositivos diferentes | Candidatas são as placas que citam o IDCODE; aviso de variante |
| 5 | Mesmo dispositivo em placas diferentes | O inventário, ou `--board`, desempata |
| 6 | Revisões do mesmo dispositivo | Aviso de que o IDCODE não prova a variante |
| 7 | IDCODE desconhecido | Erro com os IDCODEs procurados e os cabos vistos |
| 8 | Cadeia quebrada | Erro de infraestrutura; só desligar e ligar a placa resolve |
| 9 | Cabo ocupado | A trava recusa e mostra o dono; `--wait` espera |

## 7. Trava por placa

Cada placa tem um arquivo de trava, tomado com `flock` exclusivo durante a sessão inteira. O nome é o identificador da placa sem hífens mais o host (`de0cv-ws.lock`), que é o arquivo que os agentes e o runner do Tests já usam. Um host com duas placas do mesmo tipo usa o `id` do inventário, e a entrada pode fixar o arquivo com `lock_file`.

O dono grava no arquivo o host, o usuário, o processo, o comando e o instante. Quem encontra a placa ocupada lê esse registro; um `flock` comum não grava nada, e a mensagem diz isso. Sem `--wait`, a trava falha na hora, e `--wait` sozinho espera até 4 horas.

## 8. Placas sem USB-Blaster padrão

A DE10-Nano usa o USB-Blaster II, com o cabo `DE-SoC [USB-1]` e a cadeia de dois dispositivos, o HPS (`4BA00477`) e o FPGA (`02D020DD`). O FPGA é o segundo da cadeia, e a identidade do dispositivo usa a posição `@2`. O `doctor` avisa do firmware ainda não carregado (`09fb:6010`), do cabo que não aparece (`09fb:6810` sem cabo `DE-SoC`) e sugere remover o HPS da cadeia no programador diante do erro 209025, sem aplicar nada.

A MKR Vidor 4000 só tem a USB do SAMD21 (`2341:8056`). O `doctor` diz que falta carregar o sketch `USBBlaster` no SAMD21 pelo modo de bootloader, e as ferramentas não gravam o sketch.

## 9. Integração com a configuração

`riscv-tools` monta o `JtagLink` pela seleção quando `quartus.jtag_device` não está definido, ou quando `--board` ou `--board-id` é dado. Com `jtag_device` e sem essas opções, o cabo é o que lista o IDCODE dele, ou o que `--cable` força, desde que a cadeia dele liste o IDCODE. As chaves `quartus.board` (identificador ou `auto`) e `quartus.boards` (lista que o `auto` pode tomar) vêm do `platform.yaml`.

## 10. Testes

Os testes usam fixtures do `jtagconfig` (`tests/fixtures/jtagconfig`), do `lsusb` e de pacotes de placa (`tests/fixtures/boards`), sem placa nem Quartus. Cobrem os casos 1, 2, 4, 5, 6, 7, 8 e 9, a precedência, o registro no inventário, a trava com um `flock` externo, os subcomandos de ponta a ponta e o tratamento da DE10-Nano e da MKR Vidor.

```bash
uv run pytest tests/test_board_scan_select.py tests/test_board_special.py \
  tests/test_board_lock.py tests/test_board_cli.py
```

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
