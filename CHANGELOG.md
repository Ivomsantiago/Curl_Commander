# Changelog

All notable changes to CurlCommander are documented here. This release turns a
basic curl generator into a request builder and API/AppSec testing tool. Format
loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [Não lançado]

### Adicionado

* **Relatório de engajamento em HTML (`curlcmd report`).** Novo `core/report.py`
  agrega os achados validados de um engajamento num único HTML autocontido
  (CSS embutido, sem recursos externos), agrupado por severidade (reusa
  `discovery.severity_of`). Cada achado traz descrição, endpoint, severidade,
  explicação, payload, passos de reprodução (`curl` via `curl_builder`),
  evidência e remediação. Os `ValidationResult` passam a ser **persistidos** por
  engajamento numa nova tabela SQLite (`validation_results`, migração
  `PRAGMA user_version` v3→v4) sempre que `validate` (navegador/SSRF/IDOR) roda
  com `--engagement`. Tudo derivado do alvo é redigido (`redaction.redact_config`
  + máscara de segredos na query) e escapado em HTML antes de entrar no
  documento, então o relatório é seguro para compartilhar.
  `curlcmd report --engagement <nome> --out report.html`.
* **Cliente e fuzzing de WebSocket (`curlcmd ws`, extra `ws`).** O motor de fuzz
  foi refatorado para um *seam* de transporte (`fuzzer.Transport =
  Callable[[RequestConfig], Awaitable[ResponseResult]]`, parâmetro
  `transport=` em `run_fuzz`), de modo que combinação clusterbomb/pitchfork,
  filtros (`--mc/--fc/--ms/--fs/--mr`) e detecção de anomalia **não** são
  duplicados — HTTP (`http_client.send`) e WebSocket (`core/ws_client.py`)
  compartilham o mesmo caminho. `curlcmd ws connect wss://…` abre uma sessão
  interativa (prompt_toolkit) e `curlcmd ws fuzz wss://… --message '{"cmd":"FUZZ"}'
  -w payloads.txt` faz fuzz de mensagens (uma resposta por envio, correlacionada
  via lock). Conexão/sessão que fecha no meio do fuzz vira um resultado de erro
  limpo, nunca um traceback. Sem dependência nova obrigatória: o `websockets`
  é carregado sob demanda com mensagem clara de "instale o extra".
* **Importação de coleções OpenAPI e Postman (`curlcmd import`).** Novos
  `core/importers/openapi.py` e `core/importers/postman.py` (parsers manuais,
  sem dependência nova — OpenAPI YAML usa o `pyyaml` já exigido, Postman é JSON
  puro). OpenAPI 3.0/3.1: percorre `paths`, resolve `$ref` de
  `components.schemas` (com quebra de recursão) e mapeia
  `components.securitySchemes` para `auth_type/auth_value`; onde não há exemplo,
  deixa um marcador `FUZZ` pronto para o fuzzer. Postman v2.1: percorre itens
  aninhados e resolve `{{var}}` contra `--env`/`--postman-env` (export ou objeto
  plano). Cada requisição é persistida no histórico com uma etiqueta de
  proveniência (`origin`, ex.: `openapi:spec.yaml`) — nova coluna via migração
  `PRAGMA user_version` v2→v3. `--out` grava a coleção resolvida como JSON.
  `curlcmd import openapi spec.yaml --out col.json` /
  `curlcmd import postman collection.json --env env.json --out col.json`.
* **IDOR/BOLA por correlação de autorização (`curlcmd validate idor`).** Novo
  `core/idor.py`: para cada `RESOURCE_ID`, envia a **mesma** requisição como a
  identidade A (dono baseline) e como B (atacante) — só a autenticação muda — e
  compara o corpo com `difflib.SequenceMatcher`. B recebendo `200` com corpo
  estruturalmente igual ao de A ⇒ **confirmado**; B barrado com `401/403/404` ⇒
  **bloqueado**; meio-termo ⇒ **suspeito** (exige um humano, nunca confirma
  sozinho). `--fuzz-range INI-FIM` faz enumeração horizontal com a identidade B
  (reusa o fuzzer) para medir quantos recursos são realmente alcançáveis.
  `curlcmd validate idor <url com RESOURCE_ID> --ids 101,102,103 --auth-a a.json
  --auth-b b.json [--threshold 0.85] [--fuzz-range 1000-1050]`.
* **Confirmação de SSRF cega via Interactsh (OOB).** Novo `core/oob/interactsh.py`
  (extra `oob = [cryptography]`) implementa o protocolo real do
  projectdiscovery/interactsh: registro com chave RSA-2048, subdomínios de
  callback por payload (correlacionáveis), polling com decriptação
  RSA-OAEP(SHA-256) + AES-256-CFB, e deregister. Novo validador
  `core/validators/ssrf.py` e `curlcmd validate ssrf --url <…FUZZ_OOB…> --param
  <nome>`: injeta um callback único, dispara a requisição e espera a interação.
  DNS-only e conexão HTTP completa são achados **distintos** (severidade/detalhe
  diferentes), não colapsados. Consentimento explícito obrigatório
  (`--i-understand-oob`) ao usar um servidor público, ou `--interactsh-server`
  para infraestrutura própria — deixando claro que a URL de callback não é o alvo.
* **Auth macro reusável (`--auth-macro`).** Novo `core/auth_macro.py`: login
  automatizado (HTTP puro ou navegador Playwright) com extração de token
  (mini-JSONPath, ou `jsonpath-ng` via extra `auth`) e/ou cookies, e renovação
  de sessão *single-flight* — uma rajada de 401 concorrentes dispara **um** só
  login. A checagem de "sessão morta" é `401/403` por padrão, sobrescrevível com
  `--session-die-regex` (para apps que devolvem `200` com HTML de "sessão
  expirada"). Integrado a `run_fuzz`/`discover`/`bounty-scan`/`intruder` e ao
  envio de requisição única. Mutuamente exclusivo com
  `--auth-bearer/--auth-basic/--auth-apikey`. `apply()` clona o `RequestConfig`,
  nunca muta o original.

### Corrigido

* **Hang do job `test` no Windows (item 0).** A suíte podia travar num
  `recv()` de socket que nunca retornava sob o event loop Proactor do Windows.
  Correção de causa raiz: `tests/conftest.py` fixa o `WindowsSelectorEventLoopPolicy`
  no Windows; o servidor TCP de teste (`_RecordingServer`) passa a usar `accept()`
  com timeout e cleanup garantido (fecha o socket e faz `join` da thread), então
  não sobra thread órfã bloqueada. Além disso, `asyncio_default_fixture_loop_scope`
  passa a ser `function` e há uma rede de segurança `pytest-timeout` (`timeout=60`)
  que transforma qualquer hang futuro em falha rápida com traceback, em vez de
  esgotar o job de CI.

## [0.3.3] - 2026-09-06 — Correção da demo no PyPI + versão consistente

### Corrigido

* **Imagem da demo quebrada no PyPI.** O README publicado no PyPI referenciava
  a demo por caminho relativo (`docs/demo.gif`), que o PyPI não resolve (não tem
  contexto do repositório). Passa a usar a URL absoluta
  `https://raw.githubusercontent.com/Ivomsantiago/Curl_Commander/main/docs/demo.gif`
  no README PT-BR e EN, e remove a nota antiga de "espaço reservado".
* **Versão inconsistente.** `curlcommander.__version__` estava em `0.2.0`
  enquanto o pacote era `0.3.1`; ambos agora em `0.3.3`, então `curlcmd --version`
  e o metadado do PyPI batem.

> Observação: como a descrição de uma versão já publicada no PyPI é imutável, a
> correção da imagem só aparece na página do PyPI após publicar esta nova versão.

## [0.3.2] - 2026-09-06 — Corrige a URL da demo no README

### Corrigido

* A imagem de demonstração usava um caminho relativo (`docs/demo.gif`), que só
  resolve dentro do GitHub; fora dele — por exemplo na página do pacote no
  PyPI — a imagem não aparecia. Agora aponta para a URL absoluta do
  `raw.githubusercontent.com`.

## [0.3.1] - 2026-09-06 — Reorganização do changelog

### Corrigido

* Consolida entradas de changelog duplicadas e seções "não lançado" órfãs em
  um histórico único e coerente, sem mudança de código ou de API pública.

## [0.3.0] - 2026-09-06 — Correções de release e publicação

### Corrigido

* Correções de configuração e metadados de release.
* Ajustes no fluxo de publicação do pacote no PyPI via GitHub Actions.
* Correções menores sem alteração da API pública ou introdução de novas funcionalidades.

## [0.2.0] - 2026-09-06 — GUI vira "Burp na TUI"

### Adicionado

* **`curlcmd setup` prepara tudo por padrão**: sem flags e interativo, pergunta
  grupo a grupo (payloads = sim; resto = pergunta); `--yes` sem flags equivale a
  `--all --yes`.
* **Frescor de wordlists**: marcador de sync por fonte; `doctor` sinaliza fontes
  com > 30 dias e `fuzz`/`discover`/`bounty-scan` imprimem um aviso não
  bloqueante.
* **Abas Proxy / Repeater / Intruder**: GUI com `TabbedContent`, Repeater (sub-abas
  persistentes, editor raw, histórico de reenvios), Intruder (posições `§…§`,
  4 modos, grade ordenável com anomalia), Proxy (captura ao vivo, escopo esmaecido,
  "enviar para Repeater/Intruder"). Roteamento por Ctrl+R/Ctrl+I.
* **Visualizador de resposta reutilizável**: Pretty/Raw/Headers/Cookies, busca com
  contagem navegável, diff entre respostas.
* **`core/intruder.py`** mapeia os 4 modos sobre `run_fuzz`.
* **Análise passiva**: `core/passive.py` (headers de segurança, flags de cookie,
  CORS, erro verboso, fingerprint) como candidatos, com saída SARIF; botão
  **Analisar** na resposta.
* **Opções de requisição completas na GUI** (HTTP/2, compressed, cookies).

### Corrigido

* **Saída da TUI visível e robusta**: `compose()` agora inclui Header e Footer
  (os atalhos aparecem na tela), há um botão **Sair**, e Ctrl+Q/Ctrl+C saem
  mesmo com foco num Input; confirmação só enquanto há requisição em andamento.
* `send()` preservava `params=[]` e apagava a query embutida na URL; agora a
  query da URL sobrevive.

## [0.1.0] — Arquitetura e funcionalidades principais

### Adicionado

* **Ordered, case- and duplicate-preserving headers & params.** `HeaderList`
  substitui `dict`, preservando duplicatas, ordem e capitalização.
* **Raw byte-level socket transport** que bypassa httpx para testes de smuggling,
  CRLF e path-traversal.
* Importar comandos curl (`--import`, `--import-file`, `--import-clipboard`).
* Importar raw HTTP request blocks (`--import-raw --host`).
* Cookies e sessões (`--cookie`, `--cookie-jar`, `--session`).
* Multipart uploads (`-F/--form-file`).
* Asserções de resposta (`--assert-*`) com `--report json|junit`.
* `--version`, `--fail`, `--raw`.
* TUI com painel de opções, abas de resposta, busca, clipboard, keybindings, env substitution.
* Controle total de headers/params/request-line, `--no-default-headers`, `--raw-path`.
* Transporte raw (`--raw-request`), CL.TE/TE.CL sobrevivem.
* Fuzzing (`-w`, `--payloads`, clusterbomb/pitchfork, filtros `--mc/--fc/--ms/--fs/--mr`, `--concurrency`, `--rate`) com encoders.
* Biblioteca interna de payloads (sqli/xss/ssti/traversal/cmdi) esboço.
* GraphQL, SOAP/XML, gRPC-web, streaming (`--stream`).
* Escopo allowlist (`--scope`), `--dry-run`, evidência (`--evidence`, `--engagement`).
* GitHub Actions CI com ruff, mypy, matriz 3.11/3.12/3.13 × Linux/macOS/Windows, cobertura ≥80%.
* ruff, mypy `--strict`, pre-commit.
* Testes para runner, GUI, curl round-trip, redação de segredos.
* Metadados do pacote, LICENSE, CONTRIBUTING.md.
* `install.sh` prefere uv/pipx, venv fallback.
* Migrações SQLite via `PRAGMA user_version`.
* Logging estruturado (`--log-file`, `--log-level`).

### Corrigido

* Basic auth agora aparece no curl gerado (`-u user:pass`).
* `-L` emitido apenas quando redirects são seguidos.
* `--timeout` refletido como `--max-time`.
* Replay lossless: a requisição completa é armazenada e reidratada.
* Redação de segredos antes da persistência (`{{VAR}}` ou REDACTED).
* Códigos de saída significativos (`0` ok, `1` uso, `2` rede, `3` asserção, `22` HTTP ≥ 400).
* Parsing centralizado de headers/params; `-H "Accept:application/json"` não é mais ignorado.
* `--output` binário; display com decoding charset-aware.
* Truncamento de respostas grandes na tela, salvamento completo.
* JSON pretty-print automático; `--raw` desabilita.
* GUI usa uma única conexão SQLite e a fecha.

## [0.0.1] — Initial release

* Geração de curl, envio com httpx, histórico SQLite, wizard, TUI.
