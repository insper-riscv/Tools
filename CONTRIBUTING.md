# Guia de Contribuição

🌐 [Português](CONTRIBUTING.md) · [English](CONTRIBUTING.en.md)

Este documento define as regras obrigatórias de codificação, organização estrutural, documentação e verificação para qualquer contribuição ao repositório `Tools`.

## 1. Normas Python

O código segue o [PEP 8](https://peps.python.org/pep-0008) (estilo) e o [PEP 257](https://peps.python.org/pep-0257) (docstrings); o `ruff` verifica ambos (regras `E`, `W`, `N` e `D`).

### 1.1. Estilo de Código (PEP 8)

> **Desvio do PEP 8:** O PEP 8 manda escrever comentários em inglês, e este projeto os escreve em **português**. Todas as demais recomendações do PEP 8 sobre comentários se mantêm, ou seja, frases completas, sempre atualizadas e sem repetir o que o código já diz. Identificadores continuam em inglês.

| Regra | Especificação |
| :--- | :--- |
| Indentação | 4 espaços por nível; tabulações proibidas |
| Codificação | UTF-8, sem declaração de encoding no arquivo |
| Largura de linha | Máximo de 79 caracteres para código; 72 para docstrings e comentários; limites definidos em `pyproject.toml` |
| Nomenclatura | `snake_case` para funções, métodos, variáveis e módulos; `PascalCase` para classes; `UPPER_SNAKE_CASE` para constantes; prefixo `_` para nomes internos |
| Imports | No topo do arquivo, um por linha, em três grupos separados por linha em branco (biblioteca padrão, terceiros, projeto), cada grupo em ordem alfabética; imports absolutos (relativos proibidos); `import *` proibido |
| Linhas em branco | Duas entre definições de nível de módulo; uma entre métodos |
| Espaços | Um espaço ao redor de operadores e após vírgulas; nenhum espaço antes de `(` de chamada, dentro de colchetes ou ao final da linha |
| Comparações | `is` e `is not` para `None`; `if seq:` em vez de `if len(seq):`; nunca `== True` ou `== False` |
| Exceções | `except` sempre com a exceção específica; `except:` sem tipo proibido |
| Comentários | **Em português** (desvio do PEP 8); frases completas, com inicial maiúscula, em linha própria ou após dois espaços no fim do código, iniciados por `# `; explicam o porquê, não repetem o que o código faz |
| Idioma | Identificadores em **inglês**; comentários em **português** |

### 1.2. Docstrings (PEP 257)

| Regra | Especificação |
| :--- | :--- |
| Escopo | Todo módulo, classe, função e método públicos tem docstring |
| Delimitador | Aspas triplas duplas (`"""`), inclusive em docstrings de uma linha |
| Resumo | Primeira linha na mesma linha das aspas de abertura, no modo imperativo, terminada em ponto |
| Docstring de uma linha | Aspas de fechamento na mesma linha, sem linha em branco antes ou depois do texto |
| Docstring de várias linhas | Resumo, linha em branco, descrição detalhada; aspas de fechamento sozinhas na última linha |
| Classes | Docstring na classe, não no `__init__`; linha em branco após a docstring |
| Seções | Estilo NumPy (`Parameters`, `Returns`, `Raises`, `Examples`), com o tipo repetindo a anotação |
| Idioma | Português |

```python
def fetch_user(user_id: str, include_roles: bool = False) -> User:
    """Busca um usuário pelo identificador.

    Parameters
    ----------
    user_id : str
        Identificador único do usuário.
    include_roles : bool, optional
        Inclui a lista de papéis na resposta, por padrão False.

    Returns
    -------
    User
        Dados do usuário.
    """
```

### 1.3. Ferramentas e Processo

| Regra | Especificação |
| :--- | :--- |
| Gerenciador | `uv` (`uv add`, `uv sync`, `uv run`); `pip`, `pip install` e `python -m pip` são proibidos |
| Testes | `pytest`; todo comportamento novo acompanha um teste |
| Tipagem | Anotações completas, verificadas pelo Pyright e pelo Pyrefly, ambos em modo `strict` |
| Estilo e qualidade | `ruff` para lint e formatação; `deptry` para dependências declaradas e usadas |
| Complexidade e duplicação | `complexipy` com máximo de 10 por função; `codeclone` para código duplicado |
| Segurança | `semgrep` para análise estática; `uv audit` para vulnerabilidades nas dependências |

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

Qualquer alteração em código, configuração ou documentação deve passar sem erros pelos comandos abaixo antes do envio. Supressões (`# noqa`, `# type: ignore`, `# nosec`) são proibidas; corrija a causa raiz.

```bash
uv run ruff check .                  # Análise estática e estilo
uv run ruff format . --check         # Formatação
uvx pycodestyle --max-line-length=79 --max-doc-length=72 --ignore=E203,W503 src tests  # Estilo PEP 8 (E203 e W503 contradizem o próprio PEP 8)
uvx pydocstyle --convention=pep257 src tests  # Docstrings PEP 257
uv run pyright                       # Tipos em modo estrito
uvx pyrefly check                    # Segundo verificador de tipos em modo estrito
uv run deptry .                      # Dependências declaradas e usadas
uvx complexipy .                     # Complexidade cognitiva máxima de 10 por função
uvx codeclone . --fail-on-new        # Código duplicado novo
uvx semgrep scan --config p/python --error .  # Análise de segurança
uv audit                             # Vulnerabilidades nas dependências
uv run pytest                        # Suíte de testes
```

Ao adicionar, renomear ou remover qualquer arquivo versionado, atualize imediatamente:
- `docs/pt-br/` e `docs/en/`
- `README.md`, `README.en.md` e a documentação afetada

---

Copyright 2026 Insper. Licenciado sob a [Apache License, Version 2.0](LICENSE).
