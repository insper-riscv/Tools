# Guia de Contribuição

🌐 [Português](CONTRIBUTING.md) · [English](CONTRIBUTING.en.md)

Este documento define as regras obrigatórias de codificação, organização estrutural, documentação e verificação para qualquer contribuição ao repositório `Tools`.

## 1. Normas Python

| Regra | Especificação |
| :--- | :--- |
| Gerenciador | `uv` (`uv add`, `uv sync`, `uv run`); `pip`, `pip install` e `python -m pip` são proibidos |
| Testes | `pytest`; todo comportamento novo acompanha um teste |
| Documentação de código | Docstrings no estilo NumPy em módulos, classes e funções públicas |
| Tipagem | Anotações completas, verificadas pelo Pyright em modo `strict` |
| Estilo e qualidade | `ruff` para lint e formatação; `deptry` para dependências declaradas e usadas |
| Nomenclatura | Identificadores em **inglês** com `snake_case`; comentários e docstrings em **português** |

## 2. Organização em Módulos

Cada módulo do pacote (a tabela do `README.md` lista todos) tem exatamente um trabalho. Ao adicionar ou
alterar código:

- Funcionalidade nova que não cabe na responsabilidade de um módulo existente
  ganha o **seu próprio módulo novo**; não a encaixe no módulo não relacionado
  mais próximo só porque é conveniente importar dele.
- Lógica necessária a **dois ou mais** módulos vira um módulo próprio (ou um
  pequeno helper privado compartilhado por import explícito), em vez de ser
  copiada em cada chamador. Duplicação entre módulos é como uma correção
  aplicada a uma cópia deixa a outra quebrada em silêncio, sem nada nos
  pontos de chamada indicando que existe uma segunda cópia.
- Se houver dúvida entre uma responsabilidade nova e uma que cabe num módulo
  existente, prefira o módulo menor e mais específico: juntar dois módulos
  depois é fácil; desembaraçar um módulo que acumulou vários trabalhos
  distintos não é.

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
