# `board_video`

Resolve o vídeo que uma plataforma pede numa placa: escolhe o modo, confere a proporção, a largura do canal de cor, o relógio de pixel e o framebuffer, e entrega os generics de temporização para o topo gerado.

## 1. Função

O pacote de placa declara o que a saída de vídeo oferece (`io.video` do `board.yaml`), o catálogo `boards/video-modes.yaml` guarda a temporização de cada modo uma só vez, e a plataforma pede o que quer em `io.video` do `platform.yaml`. Este módulo junta os três e produz um `VideoPlan`, com o modo, a largura do canal e o tamanho do framebuffer. A leitura dos três arquivos é a do [board_schema](board_schema.md).

## 2. Escolha do modo

A tabela lista os pedidos em ordem de precedência.

| Pedido da plataforma | Modo escolhido |
| :--- | :--- |
| Sem `io.video`, ou `io.video` vazio | O `default_mode` da placa |
| Só `aspect` | O modo de maior área, entre os `modes` da placa, que tem aquela proporção; no empate, a menor taxa de atualização |
| `width` e `height` | O modo do catálogo com aquele tamanho; entre taxas diferentes, o `default_mode`, depois um modo que a placa lista, depois a menor taxa |
| `width`, `height` e `aspect` | Como `width` e `height`, e a proporção do modo tem de ser a pedida |
| `refresh_hz` com tamanho ou proporção | Restringe os candidatos à taxa pedida |

Uma plataforma que lista o periférico `VIDEO` em `peripherals` e não escreve `io.video` pede o modo padrão. A proporção de um modo é a razão entre largura e altura em termos mínimos, de modo que `1280x1024` é `5:4` e nenhuma das duas proporções aceitas o cobre.

## 3. Validações

| Regra | Erro quando |
| :--- | :--- |
| V20 | O modo não existe no catálogo, a proporção não bate com `width` e `height`, o modo não consta em `modes` da placa e falta `outside_manual: true`, o `channel_bits` pedido passa do da placa, o framebuffer é maior que a área visível ou a placa não tem `io.video` |
| V21 | O relógio de pixel não pode ser gerado pelo PLL da placa junto com os relógios da plataforma |
| V22 | O framebuffer não cabe nos blocos de memória que o resto da plataforma deixa livres |

Com `outside_manual: true` um modo fora de `modes` vira o aviso V20, porque o monitor pode não aceitá-lo.

### 3.1. Relógio de pixel

O relógio de pixel é mais uma saída do PLL que já gera os relógios do `platform.yaml`, então a conferência resolve todos juntos com o mesmo cálculo do [pll_generator](pll_generator.md) (VCO único, divisores inteiros, número de saídas da família). A mensagem diz se o relógio de pixel já falha sozinho a partir da referência da placa ou se o conflito é com os outros relógios.

### 3.2. Framebuffer

Cada pixel guarda os três canais, ou seja, $3 \cdot \text{channel\_bits}$ bits, e o framebuffer ocupa

$$
\left\lceil \frac{\text{fb\_width} \cdot \text{fb\_height} \cdot 3 \cdot \text{channel\_bits}}{\text{bits\_per\_block}} \right\rceil
$$

blocos de memória. O livre é a capacidade da placa menos os blocos que a estimativa de [fit_estimate](fit_estimate.md) calcula para o perfil. Sem a tabela de calibração da família, a conferência compara com o total do dispositivo. Sem `fb_width` e `fb_height` o framebuffer tem a área visível do modo.

## 4. Generics para o topo

O `VideoPlan.generics()` escreve as associações abaixo, e `top_generator.video_generics` as entrega a partir do `TopSpec`. O `Generated` do `board_generate` traz o plano em `video`.

| Generic | Valor |
| :--- | :--- |
| `video_kind` | `"vga"` ou `"hdmi"` |
| `video_channel_bits` | 4 ou 8 |
| `video_fb_width`, `video_fb_height` | Tamanho do framebuffer |
| `video_h_visible`, `video_h_front_porch`, `video_h_sync`, `video_h_back_porch`, `video_h_total` | Temporização horizontal, em pixels |
| `video_v_visible`, `video_v_front_porch`, `video_v_sync`, `video_v_back_porch`, `video_v_total` | Temporização vertical, em linhas |
| `video_h_sync_positive`, `video_v_sync_positive` | `true` quando o pulso de sincronismo é alto |

O topo gerado ainda não instancia o periférico de vídeo, e os pinos de vídeo ainda não viram portas do topo. O mapa de generics do SoC não recebe os generics acima.

## 5. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_board_video.py` | Leitura do papel `video` e do catálogo de modos, o pedido da plataforma (inclusive `16:9` sem aspas), a escolha do modo, as regras V20 a V22, os generics e a conferência do catálogo |
| `tests/test_board_video_generate.py` | O plano chega ao `Generated`, o topo gerado não muda, os generics saem do `TopSpec` e o gerador recusa um pedido impossível |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
