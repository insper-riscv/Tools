# `pll_generator`

Calcula os contadores do PLL e escreve a primitiva da família (`altera_pll` na Cyclone V e `altpll` nas demais).

## 1. Função

Substitui a edição por expressão regular do arquivo do PLL. Mudar a frequência do núcleo é gerar o PLL de novo com outro `clocks.core.mhz`.

## 2. Cálculo

Para a referência $f_{ref}$ e os relógios pedidos, `solve` busca o menor VCO $f_{vco} = f_{ref} M / N$ dentro da faixa `vco_mhz` da família tal que

$$ \frac{f_{vco}}{f_i} \in \{1, \dots, 511\} \quad \text{e} \quad \phi_i \in \mathbb{Z} \cdot \frac{1}{8 f_{vco}} $$

para cada saída $i$. A segunda condição diz que a fase é múltiplo de um oitavo do período do VCO, e para a DE0-CV ela escolhe o VCO de 1000 MHz (passo de 125 ps), o mesmo do PLL escrito à mão. Sem solução, ou com mais saídas que `outputs_max`, o erro nomeia os pedidos (V7 e V15).

## 3. Primitiva por família

| IP da família | Escritor |
| :--- | :--- |
| `altera_pll` (Cyclone V, que inclui a DE10-Nano) | Parâmetros por saída e atribuições de instância de compensação, reset e largura de banda |
| `altpll` (Cyclone IV E, MAX 10, Cyclone 10 LP) | Razão multiplicador/divisor e fase por saída, família no `intended_device_family`, instância interna `altpll_component` |

A escolha segue a medição de síntese por família: o `altera_pll` só sintetiza na Cyclone V (erro 12024 nas outras), e o `altpll` sintetiza nas quatro. Os dois escritores compartilham o cálculo de VCO, divisores e fase (`solve`) e registram-se em `RENDERERS`. Outra primitiva entra por `register_renderer(ip, função)`, com a função `(módulo, solução, família) -> RenderedPll`; um IP sem escritor falha com `PllIpPendingError`.

## 4. Testes

| Teste | O que verifica |
| :--- | :--- |
| `tests/test_pll_generator.py` | VCO de 1000 MHz da DE0-CV, texto igual ao PLL à mão, fase fora do passo, divisor inexistente, V15 e o ponto de extensão `altpll` |

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](../../../LICENSE).
