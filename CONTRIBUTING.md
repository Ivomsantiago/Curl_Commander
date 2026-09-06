# Contribuindo com o CurlCommander

Obrigado por ajudar a melhorar o CurlCommander. Este projeto é um construtor de
requisições HTTP no terminal e ferramenta de testes de API/AppSec; correção e
fidelidade byte a byte importam, então mudanças vêm acompanhadas de testes.

> 🌐 This document is also relevant to English speakers — the commands are
> universal; ask in an issue if you need an English review.

## Ambiente de desenvolvimento

```bash
uv venv && source .venv/bin/activate     # ou: python -m venv .venv
uv pip install -e ".[dev]"               # ou: pip install -e ".[dev]"
pre-commit install                       # opcional: roda as checagens no commit
```

## Arquitetura

Camadas estritas — `core/` nunca pode importar de `cli/` ou `gui/`:

- `core/` — modelo de requisição, builder/parser de curl, transportes (httpx +
  socket cru), redação, fuzzing, asserções, encoders, escopo, evidência,
  registro de recursos opcionais (`core/features.py`).
- `storage/` — histórico em SQLite com migrações via `PRAGMA user_version`.
- `cli/` — argparse, orquestração, wizard, `setup`/`doctor`/`self-update`.
- `gui/` — TUI em Textual.

## Antes de abrir um PR

Rode o gate completo localmente — a CI roda o mesmo:

```bash
ruff check .
ruff format --check .
mypy                     # estrito em core/ e storage/
pytest --cov=curlcommander
```

Diretrizes:

- **Toda mudança de comportamento vem com teste.** Correções de bug ganham um
  teste de regressão que falha antes e passa depois.
- **Mantenha o `mypy --strict` limpo** em `core/` e `storage/`; adicione tipos.
- **Nenhuma dependência de runtime nova** sem justificativa; recursos opcionais
  vão em `[project.optional-dependencies]` e no registro `core/features.py`.
- **Nunca persista um segredo.** Tudo que é escrito no banco de histórico, no
  export JSON, em evidências ou logs deve passar pela camada de redação.
- **Mensagens ao usuário em português**, sempre com a ação de correção.
- Um commit focado por mudança, com prefixo `fix:` / `feat:` / `chore:` /
  `test:` / `docs:`.

## Escopo de testes de segurança

Esta ferramenta é para testes de segurança **autorizados**. Ao adicionar
recursos de pentest, mantenha as travas de segurança intactas: a imposição de
escopo (`--scope`), o aviso do `--no-verify` e a redação de segredos não são
opcionais.
