# Changelog

All notable changes to CurlCommander are documented here. This release turns a
basic curl generator into a request builder and API/AppSec testing tool. Format
loosely follows [Keep a Changelog](https://keepachangelog.com/).

## Versionamento

Este projeto **não** segue o SemVer padrão. Dada uma versão `X.Y.Z`:

- **X** (primeiro número) sobe a cada mudança de código, novas funções ou
  melhorias — funcionalidade nova ou reescrita relevante.
- **Y** (segundo número) sobe para correções gerais (bugs) que não introduzem
  funcionalidade nova.
- **Z** (terceiro número) sobe para patches de segurança, correções de
  pipeline/CI e melhorias de build/empacotamento — sem mudança de
  funcionalidade ou de API pública.

## [Não lançado]

### Corrigido

* O instalador do Windows não encerra mais depois de uma instalação bem-sucedida
  via `uv` quando `uv tool update-shell` escreve a mensagem informativa
  `already in PATH` no stderr. No Windows PowerShell 5.1, essa saída era
  convertida em `NativeCommandError` por `$ErrorActionPreference = 'Stop'`.
  A atualização de PATH agora é tratada como best-effort, baseada no exit code
  nativo, tanto para `uv` quanto para `pipx`.

## [7.0.0] - 2026-09-10 — Extração dos handlers de histórico da CLI

### Alterado

* Extraídos os handlers de listagem, exibição de cURL, exportação e exclusão
  do histórico para `curlcommander.cli.commands.history`, reduzindo as
  responsabilidades de `cli/runner.py` sem alterar os subcomandos, mensagens
  ou códigos de saída existentes.
* O dispatcher da CLI continua responsável pelo ciclo de vida do repositório,
  enquanto as operações de histórico recebem explicitamente o console usado
  para apresentar seus resultados.

### Distribuição

* Versão do pacote e do comando `curlcmd --version` atualizadas para `7.0.0`.
* A tag `v7.0.0` aciona o workflow de release existente, que executa os quality
  gates, gera os binários multiplataforma, cria a GitHub Release e publica o
  wheel e o sdist no PyPI por Trusted Publishing.

## [6.0.3] - 2026-09-09 — Corrige deadlock (Timeout) na suíte de testes (Windows)

### Corrigido
* Corrige travamento (timeout de 60s) nos testes da interface gráfica (`test_gui.py`) que ocorria no CI (`windows-latest`) e localmente ao executar a suíte completa com `pytest-asyncio >= 0.24`. Testes que tentavam disparar a saída prematura da aplicação (`app.exit()`) via teclas de atalho podiam resultar em *deadlocks*.

## [6.0.2] - 2026-09-09 — Corrige validação de fumaça (smoke test) no macOS

### Corrigido

* **Pipeline de Release (`build-binary`) falhava em macOS (x64/arm64)**: O comando de validação (`grep`) falhava ao detectar o path do Chromium empacotado devido a quebras de linha introduzidas pelo formatador de tabelas (rich) em ambientes CI sem TTY.

## [6.0.1] - 2026-09-09 — Corrige erros de tipagem do mypy (CI)

### Corrigido

* **Build CI falhando no mypy**: Corrigidos erros de tipagem em `curlcommander/core/graphql.py` (instanciação do `RequestConfig` e extração da schema).

## [6.0.0] - 2026-09-09 — OAuth2, GraphQL, Visual Diff, Docker e correções de lint

### Adicionado

* **Gerenciador OAuth2 / OIDC** (`curlcommander/core/auth_oauth2.py`):
  - Suporte a fluxos `client_credentials`, `password`, `authorization_code` (com PKCE S256).
  - Renovação automática de tokens via `refresh_token` com cache e detecção de expiração.
* **Ferramentas GraphQL** (`curlcommander/core/graphql.py`):
  - Executor de Introspection Query para mapeamento automático de schema.
  - Construtor de requisições GraphQL com payload JSON (queries, variables, operationName).
* **Painel de Visual Diff** (`curlcommander/gui/diff_panel.py`):
  - Comparador de respostas HTTP (headers + body) com diff unificado lado a lado na TUI.
* **Ambiente Docker** (`Dockerfile`, `docker-compose.yml`):
  - Imagem Python 3.12 Slim pré-configurada com Playwright/Chromium e Go toolchain.

### Corrigido

* **Lint (`ruff check`) falhava no CI** — corrigidos 10 erros em 7 arquivos:
  - Imports não utilizados removidos (`auth_oauth2.py`, `diff_panel.py`, `test_auth_oauth2.py`,
    `test_diff_panel.py`, `test_graphql.py`).
  - Blocos de import reorganizados (`diff_panel.py`, `test_graphql.py`).
  - `UP038` em `headers.py`: `isinstance(x, (A, B, C))` → `isinstance(x, A | B | C)`.
  - `C416` em `proxy.py`: list comprehension desnecessária → `list()`.

## [5.1.1] - 2026-09-09 — Corrige detecção de Chromium em pacotes .app e macOS x64

### Corrigido

* **`build-binary (full)` falhava no smoke test de Chromium no macOS (x86_64 / arm64)**:
  - `curlcommander/core/browser.py::chromium_executable` expandido para detectar pacotes `.app` com qualquer nome (ex: `Google Chrome for Testing.app`) e subdiretórios de arquitetura (`chrome-mac-x64`, `chrome-mac-arm64`).
  - Adicionado suporte a executáveis dentro de pacotes `.app` e fallbacks para headless shell.
  - Atualizada a suíte de testes unitários para validar layouts macOS e Windows.

## [5.1.0] - 2026-09-08 — Corrige detecção de Chromium/features no binário "full"

### Corrigido

* **`build-binary (full)` falhava no smoke test de Chromium bundled** (`curlcmd
  doctor` não reportava o Chromium empacotado com as variáveis de ambiente
  ausentes, o cenário real de um usuário que baixa o binário standalone).
  Duas causas reais no código, não na pipeline:
  - `features.available()` usava só `importlib.util.find_spec()`, que pode
    retornar `None` para um módulo que um `import` de verdade resolve sem
    problema — comportamento já observado com `playwright` dentro do binário
    onedir "full" do PyInstaller. Sem essa linha, `doctor` nem chegava a
    imprimir a checagem de Chromium. Agora cai para um `import` real quando
    `find_spec` diz que não está disponível.
  - `packaging/rthook_chromium.py::bundled_browsers_path` só olhava
    `<base_dir>/pw-browsers`. O layout onedir padrão do PyInstaller 6+
    coloca os arquivos coletados (`COLLECT`, incluindo o `Tree()` do
    Chromium) em `_internal/`, mas `sys._MEIPASS` nem sempre concorda com
    esse split entre versões — agora verifica `<base_dir>/pw-browsers`,
    `<base_dir>/_internal/pw-browsers` e o diretório do próprio executável,
    cobrindo os layouts possíveis sem depender de fixar uma versão exata do
    PyInstaller.
  - `release.yml`: o smoke test agora imprime a saída completa do `doctor` e
    a árvore de `dist/curlcmd` quando falha, em vez de um erro opaco.
* **`curlcmd --version` reportava `4.0.0`** — `curlcommander/__init__.py`
  tinha `__version__` hardcoded, dessincronizado do `pyproject.toml` desde
  antes desta série de correções (nenhum dos releases 5.0.0–5.0.4 tocou
  nesse arquivo). Atualizado para acompanhar a versão real do pacote.

## [5.0.4] - 2026-09-08 — install-smoke-venv-windows: causa raiz real encontrada e corrigida

### Corrigido

* **Causa raiz confirmada via log real do runner (`CommandType`/`Source`
  adicionados na 5.0.3): o GitHub Actions reaplica (prepend) toda entrada de
  `GITHUB_PATH` — é assim que `actions/setup-python` registra sua própria
  pasta `Scripts` — no `Path` de **todo step seguinte**, incondicionalmente,
  pelo resto do job.** Isso desfazia silenciosamente qualquer `Path=`
  escrito em `$GITHUB_ENV` por um step anterior — exatamente o que as
  correções 5.0.1/5.0.2/5.0.3 tentavam fazer. O log mostrou `pipx.exe`
  resolvido a partir do exato diretório hostedtoolcache que já tínhamos
  "removido". Não era PATH order, não era `Path` vs `PATH`, não era profile
  do PowerShell — era a própria arquitetura de cross-step do Actions.
  Removido o step separado "Hide uv/pipx from PATH"; a exclusão (varredura
  de disco por `uv`/`pipx` em cada diretório do `Path`, criada na 5.0.2) foi
  extraída para `.github/scripts/hide-uv-pipx.ps1` e agora é feita **dentro
  do mesmo processo** de cada step que precisa da checagem (`Confirm` e
  `Run the installer`), via dot-source — sem depender de propagação entre
  steps, que nunca poderia funcionar dado o comportamento documentado do
  `GITHUB_PATH`.

## [5.0.3] - 2026-09-08 — install-smoke-venv-windows: elimina o profile do PowerShell da equação

### Corrigido

* **A varredura de disco da 5.0.2 confirmou que uv/pipx não existem como
  arquivo em nenhum diretório do `Path`** — mesmo assim `Get-Command`
  continuava resolvendo `pipx`. Como as duas correções anteriores (chave
  `Path`, depois varredura direta) já tinham eliminado qualquer explicação
  ligada a PATH, a origem só pode ser algo que o PowerShell resolve à
  revelia do PATH: uma function/alias definida no profile (a imagem do
  runner Windows é fortemente customizada, com dezenas de toolchains) ou um
  redirecionamento via registro (App Paths). `shell: pwsh` no GitHub Actions
  **não** passa `-NoProfile`, então o profile é carregado em todo step. Os
  três steps do job (`Hide`, `Confirm`, `Run the installer`) agora rodam com
  `-NoProfile` explícito — o mesmo `-NoProfile` que o step final já usava
  para o processo novo que valida `curlcmd --version`. O `Confirm` também
  passou a imprimir `CommandType`/`Source` antes de falhar, para não
  precisar de mais uma rodada de log caso a causa seja outra.

## [5.0.2] - 2026-09-08 — Corrige de vez o install-smoke-venv-windows

### Corrigido

* **A correção da 5.0.1 (chave `Path` em vez de `PATH`) era necessária mas
  não suficiente.** Com a run real do runner Windows foi possível confirmar
  (via log baixado da API do GitHub) que a troca de chave funcionou — o
  diretório do Python do `actions/setup-python` foi de fato removido do
  `Path` repassado ao próximo step. O `pipx` continuava resolvível porque
  vive em `C:\Users\<user>\AppData\Roaming\Python\Python3XX\Scripts`, uma
  cópia pré-instalada da própria imagem do runner que `Get-Command -All`
  simplesmente nunca reportou (nem com a exclusão de todos os matches, nem
  depois do fix de chave) — não era um problema de PATH/GITHUB_ENV, era o
  `Get-Command -All` não enumerar essa cópia. A etapa `Hide uv/pipx from
  PATH` agora varre o disco diretamente: para cada diretório do `Path`,
  testa a existência de `uv`/`pipx` com cada extensão de `$env:PATHEXT`, sem
  depender de resolução de comando nenhuma.

## [5.0.1] - 2026-09-08 — Corrige CI do install-smoke-venv-windows

### Corrigido

* **`install-smoke-venv-windows` (ci.yml): a exclusão de uv/pipx do PATH não
  tinha efeito no Windows.** O step escrevia `PATH=$newPath` em `$GITHUB_ENV`,
  mas a variável do sistema no Windows chama-se `Path` — escrever `PATH`
  (maiúsculo) cria uma entrada nova e distinta ao lado da `Path` original em
  vez de substituí-la, então o processo do step seguinte ainda resolvia
  `pipx`/`uv` pela `Path` antiga, não filtrada. As duas tentativas anteriores
  (excluir todos os matches do `Get-Command -All`, depois trocar `Out-File`
  por `Add-Content`) corrigiram problemas reais mas não este, e por isso o
  job continuava falhando de forma idêntica. Corrigido escrevendo a chave com
  a grafia exata `Path`.

## [5.0.0] - 2026-09-08 — GUI completa, engajamento isolado, config TOML e orquestração de recon

### Adicionado

* **Chromium embutido no binário standalone — variante "full" (item 10.3).**
  `packaging/curlcmd.spec` agora detecta em tempo de build se
  `PLAYWRIGHT_BROWSERS_PATH` aponta pra um Chromium já instalado
  (`playwright install chromium`); se sim, embute a árvore inteira no bundle
  (`pw-browsers/`) e muda automaticamente de onefile para onedir (só nesse
  caso — sem isso, o build continua onefile, byte a byte como antes: zero
  mudança para quem não pediu a variante full). Novo
  `packaging/rthook_chromium.py` aponta `PLAYWRIGHT_BROWSERS_PATH` para a
  cópia embutida via `sys._MEIPASS` (funciona em onefile e onedir sem
  distinção). `.github/workflows/release.yml` passa a publicar
  `curlcmd-<os>` (lite, inalterado) **e** `curlcmd-<os>-full.tar.gz`/`.zip`
  (Linux/macOS/Windows) por release, com um smoke test dedicado que
  *realmente lança* o Chromium embutido (não só confere se o caminho existe)
  antes de publicar — a validação cross-OS que o próprio pedido exigia antes
  de prometer que funciona em todo lugar.
  - **Corrigido en passant, achado durante a verificação local desta feature**
    (`core/browser.py::chromium_executable`): o Playwright atual baixa
    "Chrome for Testing" em `chrome-linux64`/`chrome-win64`/`chrome-mac64`
    (sufixo `-64`), não mais `chrome-linux`/`chrome-win`/`chrome-mac`. O glob
    só reconhecia o layout antigo — `curlcmd doctor` reportava Chromium como
    ausente mesmo com um Chromium funcional instalado (o `validate` ainda
    funcionava por baixo, via a resolução própria do Playwright a partir de
    `PLAYWRIGHT_BROWSERS_PATH`, mascarando o diagnóstico incorreto). Agora
    tenta os dois layouts. Sem teste anterior cobrindo esta função —
    `tests/test_browser_chromium_path.py` (novo) cobre ambos os layouts.
* **Wordlist essencial embutida para `discover` (item 10.2).** Rodar
  `discover` sem `-w`/`--payloads` antes de qualquer `payloads sync` recusava
  o comando; agora usa `curlcommander/data/payloads/discovery-essentials.txt`
  (~385 caminhos comuns curados pelo próprio projeto — `.env`, `.git/config`,
  `admin`, `wp-admin`, `api/v1`, backups, painéis administrativos etc.) como
  padrão, com aviso indicando `curlcmd payloads sync seclists` para cobertura
  completa. Uma fonte explicitamente pedida que resolve vazia continua
  recusando (o fallback só entra quando nada foi pedido). Reaproveita o
  mecanismo já existente de listas embutidas (`core/payloads.py`), sem novo
  subsistema.
* **Cinco novas abas na GUI (item 9): Validar, Recon, Achados, WebSocket +
  barra de status.** A TUI ganhou paridade com a CLI para os fluxos que só
  existiam via linha de comando:
  - **Validar** — formulário sobre `core.validators.*` (xss/cors/
    open-redirect/clickjacking/csrf/ssrf/idor), campos por categoria, mesmas
    cores de veredito da CLI, e persistência automática via o novo
    `core/validation_store.py` (extraído de `cli/runner.py::_persist_validation`
    para que CLI e GUI compartilhem o mesmo caminho de redação — nunca dois
    lugares redigindo evidência de formas que podem divergir).
  - **Recon** — árvore domínio→subdomínios→URLs vivas→achados do nuclei por
    severidade, alimentada ao vivo por `core.recon.scan` (subfinder→httpx→
    nuclei); promove uma URL para o Repeater.
  - **Achados** — tabela ao vivo de `validation_results` do engajamento
    ativo, agrupável por severidade, com botão para gerar e abrir o relatório
    HTML (`core.report.build_report`).
  - **WebSocket** — cliente interativo (extra `[ws]`) com colunas separadas
    de enviado/recebido, sobre `core.ws_client.WSClient`.
  - **Barra de status** — define engajamento/escopo/macro de login uma vez
    para todas as abas, em vez de cada uma carregar sua própria cópia dos
    três campos (o equivalente em GUI do `--config` do item 8.4). Corrigida
    durante o desenvolvimento: como sibling não-dockado composto entre o
    `TabbedContent` (altura `auto`) e o `Footer` (dockado), a barra de status
    e o rodapé disputavam a mesma linha e nenhum aparecia — um container
    `auto` cujo filho pede `1fr` reivindica toda a tela restante. Corrigido
    fixando a barra de status com `dock: bottom`, com teste de regressão
    (`tests/test_gui.py::test_status_bar_stays_within_the_visible_screen`)
    checando que a região renderizada cabe na tela.
* **Arquivo único de config de engajamento (`--config`, item 8.4).** Antes,
  um engajamento que dura semanas exigia repetir `--engagement`/`--scope`/
  `--auth-macro`/`--proxy` em toda invocação — e como `--engagement` é uma
  string livre casada por igualdade exata, um typo criava silenciosamente um
  segundo engajamento sem nenhum aviso. Novo `curlcommander/core/
  engagement_config.py` lê um TOML (stdlib `tomllib`, sem dependência nova)
  com `[engagement] name/scope_file/auth_macro/proxy` uma vez; `--config
  ARQUIVO.TOML` preenche essas flags só onde a chamada atual as deixou em
  branco — qualquer flag explícita na linha de comando sempre vence sobre o
  arquivo. Disponível em toda a superfície que já aceita essas flags
  (requisição normal, `discover`, `bounty-scan`, `validate`, `proxy`,
  `report`, `history`/`replay`/`curl`/`export-history`/`delete-history`/
  `clear-history`). `report --engagement` deixa de ser obrigatório na flag
  (pode vir só do `--config`), mas continua obrigatório em algum dos dois.
* **Isolamento de dados por engajamento (`curlcmd engagement`, item 8.1).**
  Antes, todo teste rodado — de qualquer cliente, em qualquer data — vivia no
  mesmo `history.db` global; um problema de confidencialidade real (LGPD/NDA
  costumam exigir apagar os dados de um cliente ao fim do engajamento), não só
  de organização. `--engagement NOME` em qualquer comando que já aceita a flag
  (requisição normal, `validate`, `bounty-scan`, `proxy`, `report`, e agora
  também `history`/`replay`/`curl`/`export-history`/`delete-history`/
  `clear-history`) passa a isolar histórico + achados persistidos em
  `<diretório de dados>/engagements/NOME/history.db`, um arquivo por cliente.
  Novo `curlcmd engagement list` (lista com contagem de registros) e
  `curlcmd engagement delete NOME` (apaga um engajamento inteiro num comando
  auditável — exige digitar o nome de volta para confirmar, ou `--yes` em
  scripts). O nome do engajamento é validado contra path traversal antes de
  virar um nome de diretório.
* **Orquestração de recon externo (`curlcmd recon`, item 7).** Novo
  `core/recon/` cobre a fase anterior ao ataque (enumeração de superfície) sem
  reimplementar ferramentas maduras em Python: `subfinder`, `httpx-projectdiscovery`,
  `nuclei` e `katana` são detectados no `PATH` (nunca instalados/baixados pelo
  curlcmd — `curlcmd doctor` só sinaliza presença/ausência), executados via
  `asyncio.create_subprocess_exec` (argv em lista, nunca string de shell) e
  streamados como JSON/JSONL linha a linha (`-json`/`-jsonl -silent`, nunca
  scraping de texto). Escopo é aplicado antes de qualquer coisa tocar a rede:
  `subfinder -d`/`katana -u` recusam um alvo único fora do escopo
  (`ScopeError`, mesma recusa dura de `validate`/`proxy`); `httpx -l`/`nuclei -l`
  filtram a lista de hosts/URLs antes de repassar pro binário — um host fora
  do escopo nunca chega a ser sondado.
  `curlcmd recon subfinder -d alvo.com --scope scope.txt --out subs.jsonl`,
  `curlcmd recon httpx|nuclei -l lista.txt --scope scope.txt`,
  `curlcmd recon katana -u https://alvo.com --scope scope.txt`.

### Corrigido

* **Evidência de validação agora é redigida antes de persistir.** `evidence`
  (requisição crua capturada via Interactsh, snapshot de DOM, cadeia de
  redirect, ...) podia carregar `Authorization`/`Cookie`/segredo em query
  string do alvo real e ia para o SQLite (e depois pro relatório HTML) sem
  nenhuma redação — só `html.escape()` no render, que não remove o segredo,
  só o torna não-clicável. Nova `redaction.redact_evidence()` mascara linhas
  de cabeçalho sensíveis e query strings com nome de credencial em qualquer
  string/lista/dict dentro do evidence; aplicada em `_persist_validation`
  (então nunca toca o disco) e de novo em `report.py` como defesa em
  profundidade.
* **`curlcmd report` agora agrega histórico e candidatos do `bounty-scan`,**
  não só achados de `validate`. Requisições normais com `--engagement`
  ganham uma tag `engagement` no histórico (migração `PRAGMA user_version`
  v4→v5) e aparecem como apêndice no relatório; candidatos de `bounty-scan`
  passam a ser persistidos como `ValidationResult` (veredito `CANDIDATE`,
  nunca confirmado) e aparecem na seção "não conclusivos" do relatório.
* **Severidade unificada numa única fonte de verdade.** `report.py` tinha uma
  segunda tabela `_EXTRA_SEVERITY` divergente de `discovery._SEVERITY` — as
  categorias foram fundidas na tabela de `discovery.py`. Um validador agora
  também pode marcar a severidade de uma instância específica via
  `evidence["severity"]` (usado pelo SSRF: DNS-only vs. conexão HTTP
  completa são achados de severidade diferente, não mais colapsados).
* **IDOR: uma negação (401/403/404) que "vaza" o corpo de A não é mais
  auto-classificada como `blocked`.** Se A viu o recurso (200) e a resposta
  de negação de B ainda é estruturalmente igual ao corpo real de A (ex.: uma
  página de erro que ecoa o objeto para debug), isso cai em `suspect` para
  revisão humana em vez de confirmar cegamente que o controle de acesso
  funciona.
* **Um único mecanismo de substituição `{{VAR}}`.** `cli/runner.py` tinha uma
  `_substitute_variables` própria, duplicando `redaction.reveal_text` (já
  usado por `auth_macro.py` e por `--reveal`). Removida a duplicata; todo
  `{{VAR}}` no projeto resolve pela mesma função agora.
* **`scripts/install.ps1` não atualizava o PATH de verdade (item 11).** No
  branch `Install-WithVenv` (uv e pipx ausentes — o caso mais comum num
  Windows limpo), o aviso de "adicione ao PATH" era só `Write-Host`:
  `[Environment]::SetEnvironmentVariable` nunca era chamado, então `curlcmd`
  ficava permanentemente ausente do PATH após `irm | iex`. Agora o instalador
  pergunta e grava o PATH de verdade (idempotente — não duplica entrada num
  reinstall) nos três métodos (`uv`/`pipx`/venv), e uma nova
  `Update-CurrentSessionPath` atualiza `$env:Path` do processo atual logo
  após qualquer mudança de PATH, então `curlcmd` já funciona na MESMA janela
  que rodou o instalador, sem precisar abrir um terminal novo. Novo job de CI
  `install-smoke-venv-windows` força a ausência de `uv`/`pipx` (garantindo que
  o branch com o bug seja realmente exercitado, o que o `install-smoke`
  existente não garantia), verifica a persistência real do PATH abrindo um
  processo novo com o PATH reconstruído só do registro (não do `$env:Path` já
  corrigido em sessão), e confirma que reinstalar não duplica a entrada.
* **Vazamento de identidade de classe entre testes via `importlib.reload`.**
  `test_config.py`/`test_proxy.py` recarregavam `curlcommander.config` para
  testar comportamento dependente de `CURLCOMMANDER_HOME` no import — mas
  `reload()` muta o `__dict__` do módulo *no lugar*, então toda classe/função
  nele (inclusive uma nova `InvalidEngagementName`) ganha uma identidade nova
  que nunca mais bate com o que outro módulo já importado capturou via
  `from config import X` antes do reload (ex.: `cli/runner.py`) — um `except`/
  `pytest.raises` correspondente simplesmente para de casar, silenciosamente,
  pro resto da sessão de teste. As duas suítes agora verificam o
  comportamento num subprocesso real em vez de recarregar o módulo compartilhado.

## [4.0.0] - 2026-09-07 — Auth macro, IDOR, SSRF OOB, WebSocket, importers e relatório HTML

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
* **mypy sem o extra `cryptography`.** O job de type-check dev-only rodava sem
  o extra `oob`; `core/oob/interactsh.py` agora tem os imports de `cryptography`
  cobertos por `ignore_missing_imports` no `[[tool.mypy.overrides]]`, e o gate de
  cobertura ≥80% volta a valer no ambiente dev-only.

## [3.0.3] - 2026-09-06 — Corrige a URL da demo no README

### Corrigido

* A imagem de demonstração usava um caminho relativo (`docs/demo.gif`), que só
  resolve dentro do GitHub; fora dele — por exemplo na página do pacote no
  PyPI — a imagem não aparecia. Agora aponta para a URL absoluta do
  `raw.githubusercontent.com`.

## [3.0.2] - 2026-09-06 — Reorganização do changelog

### Corrigido

* Consolida entradas de changelog duplicadas e seções "não lançado" órfãs em
  um histórico único e coerente, sem mudança de código ou de API pública.

## [3.0.1] - 2026-09-06 — Correções de release e publicação

### Corrigido

* Correções de configuração e metadados de release.
* Ajustes no fluxo de publicação do pacote no PyPI via GitHub Actions.
* Correções menores sem alteração da API pública ou introdução de novas funcionalidades.

## [3.0.0] - 2026-09-06 — GUI vira "Burp na TUI"

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

## [2.0.0] — Arquitetura e funcionalidades principais

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

## [1.0.0] — Initial release

* Geração de curl, envio com httpx, histórico SQLite, wizard, TUI.
