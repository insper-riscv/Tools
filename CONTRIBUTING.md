# Guia de Contribuição

🌐 [Português](CONTRIBUTING.md) · [English](CONTRIBUTING.en.md)

Este documento define as regras obrigatórias de codificação, organização estrutural, documentação e verificação para qualquer contribuição ao repositório `Tools`.

## 1. Normas C (C23)

Todo código C do projeto (programas de teste, runtime e fixtures) é escrito sob a norma **ISO/IEC 9899:2024 (C23)** e compilado com `-std=c23`, nunca com `-std=gnu23` nem com extensões do compilador que dispensem a norma.

| Regra | Especificação |
| :--- | :--- |
| Norma da linguagem | C23 (`-std=c23`) em todos os arquivos `.c` e `.h` |
| Avisos | `-Wall -Wextra -Wpedantic -Werror`; nenhum aviso é aceito |
| Tipos de largura fixa | `<stdint.h>` (`uint32_t`, `int32_t`) em vez de `int`/`long` quando a largura importa |
| Palavras-chave de C23 | Usar `bool`, `true`, `false`, `nullptr`, `constexpr`, `static_assert` sem mensagem e `typeof`; não incluir `<stdbool.h>` nem definir `NULL` próprio |
| Atributos | Usar a sintaxe padrão `[[nodiscard]]`, `[[maybe_unused]]` e `[[noreturn]]` em vez de `__attribute__` |
| Constantes | `constexpr` ou `enum` no lugar de macros `#define` numéricas; literais binários (`0b1010`) e separadores (`1'000'000`) permitidos |
| Ambiente freestanding | Código bare-metal compilado com `-ffreestanding` depende apenas dos cabeçalhos garantidos pela norma e da libc do runtime |
| Nomenclatura | Identificadores em **inglês** com `snake_case`, constantes e macros em `UPPER_SNAKE_CASE`, tipos com sufixo `_t`; comentários em **português** |
| Comentários | Cada função e cada variável global recebem um comentário descritivo em português imediatamente acima da declaração |

A norma de referência é a [ISO/IEC 9899:2024](https://www.iso.org/standard/82075.html). Em trabalhos acadêmicos, cite-a com a entrada BibTeX abaixo:

```bibtex
@misc{iso9899,
  title        = {Information technology, Programming languages, C},
  author       = {{ISO/IEC}},
  year         = {2024},
  note         = {ISO/IEC 9899:2024 (C23)},
  howpublished = {\url{https://www.iso.org/standard/82075.html}}
}
```

## 2. Normas Python

| Regra | Especificação |
| :--- | :--- |
| Gerenciador | `uv` (`uv add`, `uv sync`, `uv run`); `pip`, `pip install` e `python -m pip` são proibidos |
| Testes | `pytest`; todo comportamento novo acompanha um teste |
| Documentação de código | Docstrings no estilo NumPy em módulos, classes e funções públicas |
| Tipagem | Anotações completas, verificadas pelo Pyright em modo `strict` |
| Estilo e qualidade | `ruff` para lint e formatação; `deptry` para dependências declaradas e usadas |
| Nomenclatura | Identificadores em **inglês** com `snake_case`; comentários e docstrings em **português** |

## 3. Regras de Documentação Markdown

Todo `README` e todo `CONTRIBUTING` e `AUTHORS` mantêm versões espelhadas em português (`*.md`) e em inglês (`*.en.md`), obedecendo às seguintes regras:

1. **Seletor de idioma e rodapé de licença:** todo `README.md` e `README.en.md` traz no topo o seletor `🌐 [Português](...) · [English](...)`, e todo arquivo `.md` encerra com o rodapé de copyright e link para `LICENSE`.
2. **Seções numeradas e progressivas:** todas as seções a partir de `##` devem ser numeradas (`## 1.`, `### 1.1.`, `## 2.`) em ordem lógica de leitura.
3. **Pontuação direta:**
   - **Proibido o uso de travessão** em prosa ou tabelas; utilize vírgula, parênteses, ponto e vírgula ou dois-pontos conforme a relação sintática real.
   - **Proibidos dois-pontos encadeados** (mais de um `:` na mesma frase ou célula de tabela).
4. **Explicação de comportamento:** nunca cite o nome de um arquivo, módulo ou sinal interno como se o próprio nome explicasse o que o sistema faz; descreva sempre a operação realizada.
5. **Tabelas e LaTeX sem redundância:** dados estruturados devem estar em tabelas Markdown e expressões matemáticas/lógicas em blocos LaTeX (`$$ ... $$` ou `$ ... $`), sem repetir em prosa o que a tabela ou equação já enuncia.
6. **Sem histórico ou pendências na documentação técnica:** documentos de arquitetura e contratos descrevem exclusivamente o estado atual, sem changelogs internos nem listas de tarefas futuras.
7. **Guias de uso apenas instruem:** instruções de instalação e execução dizem como fazer, sem justificar a escolha do método.

## 4. Verificação Obrigatória Antes de Abrir Pull Request

Qualquer alteração em código, configuração ou documentação deve passar sem erros pelos comandos abaixo antes do envio:

```bash
uv run ruff check .  # Análise estática e estilo
uv run pyright       # Verificação de tipos em modo estrito
uv run deptry .      # Dependências declaradas e usadas
uv run pytest        # Suíte de testes
```

Ao adicionar, renomear ou remover qualquer arquivo versionado, atualize imediatamente:
- `docs/pt-br/` e `docs/en/`
- `README.md`, `README.en.md` e a documentação afetada

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](LICENSE).
