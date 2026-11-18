# `boot_size`

Monta a BOOT de uma plataforma com a toolchain e mede o seu tamanho contra o da BOOT_MEMORY, antes de qualquer hardware. O linker script gerado já tem um `ASSERT` que reprova uma BOOT grande demais, mas ele só dispara quando alguém liga a BOOT. A medida daqui roda no CI e na máquina do desenvolvedor, e diz quanto cada arquivo pesa.

## 1. Entradas

Tudo vem do `platform.yaml`, sem `--config`.

| Dado | Origem |
| :--- | :--- |
| Linker script | `generate.boot_ld` |
| Fonte da BOOT | `boot_memory.S`, na mesma pasta do linker script |
| Limite | Tamanho da primeira região, a BOOT_MEMORY |
| `-march` e `-mabi` | A base e a largura do bloco `core` (`rv32i`, `rv32e`, `rv64i` ou `rv64e`), só a base, sem as extensões |

O `boot_memory.S` inclui os cabeçalhos gerados (`memory_map.h`, `boot_config.h`) e os fragmentos de boot de cada extensão do núcleo, então os cabeçalhos precisam estar gerados com `generate-memory-map`.

## 2. Como mede

1. Copia o linker script gerado, sem o `ASSERT` que compara o fim da imagem com a memória e com a memória alargada, para a BOOT grande demais ser medida e não recusada. O `ASSERT` da seção de reset fica.
2. Monta e liga o `boot_memory.S` com `-g`, para que cada instrução guarde o arquivo e a linha de onde veio.
3. Lê o fim da última seção de código com `objdump -h`. O tamanho é esse endereço menos a base da BOOT_MEMORY, então a lacuna entre `_reset` e o ponto de espera (`boot.wait_restart`) conta.
4. Soma 4 bytes por instrução de cada arquivo, lidos de `objdump -d -l`, o que separa o `boot_core.S` de cada fragmento `boot.inc`.

## 3. Resultado

| Situação | Saída | Status |
| :--- | :--- | :--- |
| A BOOT cabe | `boot size OK`, o tamanho, o limite e os bytes de cada arquivo | 0 |
| A BOOT estoura | `V-B3`, o tamanho, o limite, o excesso e os bytes de cada arquivo, do mais pesado ao mais leve | 1 |
| Sem `generate.boot_ld`, sem `boot_memory.S` ou toolchain que falha | A mensagem do problema | 2 |

## 4. Uso

```bash
uv run riscv-tools --root <projeto> check-boot-size --platform src/simulation/modular/platform.yaml
```

| Opção | Efeito |
| :--- | :--- |
| `--gcc` | O compilador da toolchain, por padrão `riscv32-unknown-elf-gcc` |
| `--objdump` | O `objdump` da toolchain, por padrão `riscv32-unknown-elf-objdump` |
| `--build-dir` | Onde escrever a montagem de medida, por padrão uma pasta temporária |

Precisa da toolchain no `PATH`, que as imagens `ci-elf` e `dev_tools` do [Infra](https://github.com/insper-riscv/Infra) trazem.

## 5. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_boot_size.py` | O linker script de medida, a BOOT que cabe (tamanho e lacuna do ponto de espera), a soma de bytes por arquivo, a BOOT que estoura com o `V-B3`, a base E montada como `rv32e`, a plataforma sem `generate.boot_ld` e os status 1 e 2 do subcomando. |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
