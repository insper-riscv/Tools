# `sdram_windows`

Dá ao hospedeiro a tabela de janelas do chip de SDRAM: onde a FLASH e a RAM de uma plataforma ficam dentro do chip, para os comandos `load-flash`, `dump-ram --region` e `load-ram` converterem um endereço de byte do SoC na palavra que a porta de debug da SDRAM espera.

## 1. A janela

Uma região na SDRAM (`FLASH` ou `RAM`) é uma janela do chip.

| Campo | Significado |
| :--- | :--- |
| `base` | Primeiro endereço de byte da região no SoC |
| `size` | Bytes da região |
| `offset` | Byte do chip onde a região começa |

O endereço de byte $A$ do SoC, em $[\text{base}, \text{base} + \text{size})$, está na palavra

$$ w = \frac{\text{offset} + (A - \text{base})}{4} $$

do chip. Uma região sem `offset` mantém o endereço do SoC, e o byte do chip é o `base` módulo a menor potência de dois que percorre a região, o mesmo que o topo gerado faz.

## 2. De onde vem a tabela

| Origem | Função | Quando |
| :--- | :--- | :--- |
| `platform.yaml` | `windows_from_platform`, `windows_from_platform_file` | Os comandos recebem `--platform` |
| `memory.sdram_windows` do `config.yaml` | `windows_from_config` | Sem `--platform`; a seção repete os números da plataforma |
| `memory.ram_base` e `memory.ram_words` | `windows_from_config` | Sem a seção; a RAM é uma janela no byte 0 do chip |

```yaml
memory:
  sdram_windows:
    FLASH: {base: 0x1000, size: 0x1FFF000, offset: 0x1000}
    RAM:   {base: 0x40000000, size: 0x2000000, offset: 0x2000000}
```

## 3. Funções

| Função | Faz |
| :--- | :--- |
| `Window.word_address(address)` | Converte o endereço de byte do SoC na palavra do chip, recusando o que não é de palavra ou sai da região |
| `Window.contains(address, length)` | Diz se um trecho de bytes cabe na região |
| `window_named(windows, name)` | Acha `FLASH` ou `RAM`, sem diferenciar maiúsculas, ou levanta `WindowError` |

## 4. Testes

`tests/test_chip_split.py` cobre a conversão das três divisões (32 e 32, 48 e 16, 16 e 48 MiB), a tabela da configuração e o erro de uma região fora da SDRAM.

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
