# Changelog

All notable changes to CurlCommander are documented here. This release turns a
basic curl generator into a request builder and API/AppSec testing tool. Format
loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [0.3.3] - 2026-09-06 — Correção da demo no PyPI + versão consistente
### Corrigido
- **Imagem da demo quebrada no PyPI.** O README publicado no PyPI referenciava
  a demo por caminho relativo (`docs/demo.gif`), que o PyPI não resolve (não tem
  contexto do repositório). Passa a usar a URL absoluta
  `https://raw.githubusercontent.com/.../main/docs/demo.gif` no README PT-BR e EN,
  e remove a nota antiga de "espaço reservado".
- **Versão inconsistente.** `curlcommander.__version__` estava em `0.2.0`
  enquanto o pacote era `0.3.1`; ambos agora em `0.3.3`, então `curlcmd --version`
  e o metadado do PyPI batem.

> Observação: como a descrição de uma versão já publicada no PyPI é imutável, a
> correção da imagem só aparece na página do PyPI após publicar esta nova versão.

## [0.3.1] - 2026-09-06 — Correções de release e publicação
### Corrigido
- Correções de configuração e metadados de release.
- Ajustes no fluxo de publicação do pacote no PyPI via GitHub Actions.
- Correções menores sem alteração da API pública ou introdução de novas funcionalidades.

## [0.3.0] - 2026-09-06 — GUI vira "Burp na TUI" + defaults consertados
### Corrigido
- **Saída da TUI visível e robusta**: `compose()` agora inclui Header e Footer
  (os atalhos aparecem na tela), há um botão **Sair**, e Ctrl+Q/Ctrl+C saem
  mesmo com foco num Input; confirmação só enquanto há requisição em andamento.
- **`curlcmd setup` prepara tudo por padrão**: sem flags e interativo, pergunta
  grupo a grupo (payloads = sim; resto = pergunta); `--yes` sem flags equivale a
  `--all --yes`.
- **Frescor de wordlists**: marcador de sync por fonte; `doctor` sinaliza fontes
  com > 30 dias e `fuzz`/`discover`/`bounty-scan` imprimem um aviso não
  bloqueante.
- **Abas Proxy / Repeater / Intruder**: GUI com `TabbedContent`, Repeater (sub-abas
  persistentes, editor raw, histórico de reenvios), Intruder (posições `§…§`,
  4 modos, grade ordenável com anomalia), Proxy (captura ao vivo, escopo esmaecido,
  "enviar para Repeater/Intruder"). Roteamento por Ctrl+R/Ctrl+I.
- **Visualizador de resposta reutilizável**: Pretty/Raw/Headers/Cookies, busca com
  contagem navegável, diff entre respostas.
- **`core/intruder.py`** mapeia os 4 modos sobre `run_fuzz`.
- **Análise passiva**: `core/passive.py` (headers de segurança, flags de cookie,
  CORS, erro verboso, fingerprint) como candidatos, com saída SARIF; botão
  **Analisar** na resposta.
- **Opções de requisição completas na GUI** (HTTP/2, compressed, cookies).
- **Correção**: `send()` preservava `params=[]` e apagava a query embutida na URL;
  agora a query da URL sobrevive.

## [0.2.0] — Arquitetura e funcionalidades principais
### Architecture
- **Ordered, case- and duplicate-preserving headers & params.** `HeaderList`
  substitui `dict`, preservando duplicatas, ordem e capitalização.
- **Raw byte-level socket transport** que bypassa httpx para testes de smuggling,
  CRLF e path-traversal.
### Phase 1 — bug fixes (cada um com teste de regressão)
- Basic auth agora aparece no curl gerado (`-u user:pass`).
- `-L` emitido apenas quando redirects são seguidos.
- `--timeout` refletido como `--max-time`.
- Replay lossless: a requisição completa é armazenada e reidratada.
- Redação de segredos antes da persistência (`{{VAR}}` ou REDACTED).
- Códigos de saída significativos (`0` ok, `1` uso, `2` rede, `3` asserção, `22` HTTP ≥ 400).
- Parsing centralizado de headers/params; `-H "Accept:application/json"` não é mais ignorado.
- `--output` binário; display com decoding charset-aware.
- Truncamento de respostas grandes na tela, salvamento completo.
- JSON pretty-print automático; `--raw` desabilita.
- GUI usa uma única conexão SQLite e a fecha.
### Phase 2 — funcionalidades
- Importar comandos curl (`--import`, `--import-file`, `--import-clipboard`).
- Importar raw HTTP request blocks (`--import-raw --host`).
- Cookies e sessões (`--cookie`, `--cookie-jar`, `--session`).
- Multipart uploads (`-F/--form-file`).
- Asserções de resposta (`--assert-*`) com `--report json|junit`.
- `--version`, `--fail`, `--raw`.
- TUI com painel de opções, abas de resposta, busca, clipboard, keybindings, env substitution.
### Phase 2B — pentest & API testing
- Controle total de headers/params/request-line, `--no-default-headers`, `--raw-path`.
- Transporte raw (`--raw-request`), CL.TE/TE.CL sobrevivem.
- Fuzzing (`-w`, `--payloads`, clusterbomb/pitchfork, filtros `--mc/--fc/--ms/--fs/--mr`, `--concurrency`, `--rate`) com encoders.
- Biblioteca interna de payloads (sqli/xss/ssti/traversal/cmdi) esboço.
- GraphQL, SOAP/XML, gRPC-web, streaming (`--stream`).
- Escopo allowlist (`--scope`), `--dry-run`, evidência (`--evidence`, `--engagement`).
### Phase 3 — quality
- GitHub Actions CI com ruff, mypy, matriz 3.11/3.12/3.13 × Linux/macOS/Windows, cobertura ≥80%.
- ruff, mypy `--strict`, pre-commit.
- Testes para runner, GUI, curl round-trip, redação de segredos.
- Metadados do pacote, LICENSE, CONTRIBUTING.md.
- `install.sh` prefere uv/pipx, venv fallback.
- Migrações SQLite via `PRAGMA user_version`.
- Logging estruturado (`--log-file`, `--log-level`).

## [0.1.0] — Initial release
- Geração de curl, envio com httpx, histórico SQLite, wizard, TUI.