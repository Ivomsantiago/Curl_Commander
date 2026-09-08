# CurlCommander

**🌐 Idioma:** **Português** · [English](README.en.md)

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green.svg)](LICENSE)
[![CI](https://github.com/Ivomsantiago/Curl_Commander/actions/workflows/ci.yml/badge.svg)](https://github.com/Ivomsantiago/Curl_Commander/actions/workflows/ci.yml)
[![Releases](https://img.shields.io/github/v/release/Ivomsantiago/Curl_Commander?display_name=tag&sort=semver)](https://github.com/Ivomsantiago/Curl_Commander/releases)

Construtor de requisições HTTP no terminal, gerador de `curl` e ferramenta de
testes de API/AppSec. Monte e repita requisições, gere um `curl` fiel, importe
do DevTools ou do Burp, faça fuzzing, valide asserções e dispare requisições
byte a byte — tudo por um único ponto de entrada: `curlcmd` (também instalado
como `curlcommander`, alias com o nome do pacote).

Feito para analistas e engenheiros que precisam de requisições confiáveis o
bastante para colar num relatório de pentest, expressivas o bastante para testar
qualquer estilo de API (REST, GraphQL, SOAP/XML, gRPC-web, formulários legados)
e programáveis o bastante para rodar em CI.

Python 3.11+ · `httpx` · `rich` · `prompt_toolkit` · `textual`.

![Demonstração do CurlCommander](https://raw.githubusercontent.com/Ivomsantiago/Curl_Commander/main/docs/demo.gif)

---

## Por que não só curl?

`curl` é imbatível para uma requisição pontual e para script. Ele perde quando o
trabalho é iterativo, com estado, repetível e investigativo — o dia a dia de
quem testa API e faz bug bounty. A tabela abaixo lista só o que no curl puro dói
ou é impossível, com o comando/atalho real aqui (`GUI` = na interface `curlcmd
--gui`; `CLI` = na linha de comando):

| Tarefa | curl puro | CurlCommander |
|--------|-----------|---------------|
| Editar 1 header e reenviar | reescrever a linha inteira | **GUI** aba Repeater: edita e reenvia; histórico de reenvios na aba |
| Fuzzing com posições e filtros | `ffuf`/`wfuzz` à parte | **GUI** aba Intruder (§marca§ posição, 4 modos, grade ordenável) · **CLI** `-w lista "…/FUZZ" --mc 200` |
| Interceptar o navegador | Burp/mitmproxy à parte | **GUI** aba Proxy: captura ao vivo + "enviar para Repeater/Intruder" |
| Analisar segurança da resposta | nada | **GUI** botão Analisar (headers/cookies/CORS/erros → candidatos) |
| Lembrar o que foi enviado | o shell esquece | **CLI** `curlcmd history` (SQLite pesquisável), `replay <id>` |
| Mesma requisição em dev/staging/prod | copiar-colar | **CLI** `{{VAR}}` + `--env-file` |
| Testar (assert + exit code + JUnit) | não existe | **CLI** `--assert-status/-header/-jsonpath --report junit` |
| Não vazar token no histórico | fica no `~/.bash_history` | redação de segredo antes de persistir (padrão) |
| Confirmar XSS de verdade | impossível | **CLI** `validate xss … --engagement` (navegador real, extra `[browser]`) |

Exemplos que executam de fato:

```bash
# fuzzing com filtro por status — no curl exigiria ffuf/xargs:
curlcmd -w words.txt "https://alvo/FUZZ" --mc 200,301 --fc 404

# testar uma resposta e falhar o pipeline (exit 3) — curl não tem assert:
curlcmd --assert-status 200 --assert-jsonpath '$.user.id==42' --report junit https://api/x/me

# abrir a interface "Burp na TUI" (Repeater/Intruder/Proxy):
curlcmd --gui
```

---

## Instalação em uma linha

```bash
# Linux/macOS
curl -fsSL https://raw.githubusercontent.com/Ivomsantiago/Curl_Commander/main/scripts/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/Ivomsantiago/Curl_Commander/main/scripts/install.ps1 | iex
```

O instalador escolhe o melhor método disponível — `uv tool` → `pipx` → um venv
gerenciado com um atalho `curlcmd` — resolve o seu PATH, é idempotente e aceita
`--yes`/`-Yes` para uso em scripts/CI. Depois, rode `curlcmd setup` e
`curlcmd doctor`.

---

## Sumário

1. [Instalação](#1-instalação)
2. [Primeiros passos: `setup` e `doctor`](#2-primeiros-passos-setup-e-doctor)
3. [Segurança](#3-segurança)
4. [CLI](#4-cli)
5. [Interface no terminal (TUI)](#5-interface-no-terminal-tui)
6. [Armazenamento do histórico](#6-armazenamento-do-histórico)
7. [Bug bounty — payloads → fuzz → discover](#7-bug-bounty--payloads--fuzz--discover)
8. [Validação por navegador e proxy interceptador](#8-validação-por-navegador-e-proxy-interceptador)
9. [Desenvolvimento](#9-desenvolvimento)
10. [Roadmap](#10-roadmap)

Novo por aqui? Comece pelo guia rápido em [`docs/COMECE-AQUI.md`](docs/COMECE-AQUI.md).

---

## 1. Instalação

A forma recomendada é o instalador de uma linha (acima). Ele prioriza instalações
isoladas (`uv tool`, depois `pipx`), cai para um venv gerenciado com um atalho
`curlcmd` no PATH e nunca mexe no Python do sistema em silêncio.

<details>
<summary>Outros métodos de instalação</summary>

| Método | Comando | SO | Quando usar |
|--------|---------|----|-------------|
| **Binário standalone** | baixe `curlcmd`/`curlcmd.exe` em Releases | Win/Lin/mac | **Recomendado** se você só quer rodar — não precisa de Python |
| winget | `winget install Ivomsantiago.CurlCommander` | Windows | Gerenciador de pacotes do Windows |
| Scoop | `scoop install curlcommander` | Windows | Bucket do Scoop |
| `curlcmd.pyz` | baixe o `.pyz`, `python curlcmd.pyz` | qualquer | Tem Python, quer um arquivo só, sem instalar |
| pipx | `pipx install curlcommander` | qualquer | Instalação isolada por usuário, no PATH |
| uv | `uv tool install curlcommander` | qualquer | Igual, porém mais rápido |
| pip (dev) | `pip install -e ".[dev]"` | qualquer | Desenvolvendo/contribuindo |

Os scripts `install.sh` / `install.ps1` na raiz (rodados a partir de um checkout)
também preferem instalações isoladas e só tocam o Python do sistema com
`--break-system-packages`/`-System` após confirmação.

</details>

### Binário standalone (sem Python)

Baixe `curlcmd` / `curlcmd.exe` para o seu SO na página de
[Releases](https://github.com/Ivomsantiago/Curl_Commander/releases), confira o
checksum contra o `SHA256SUMS` e rode direto:

```bash
chmod +x curlcmd && ./curlcmd --version          # Linux/macOS
.\curlcmd.exe --version                           # Windows (PowerShell)
```

Para gerar você mesmo: `pip install -e ".[build-exe]" && pyinstaller packaging/curlcmd.spec`
(saída em `dist/`). Há também um `curlcmd.pyz` de arquivo único (precisa de
Python, sem instalar): `pip install -e ".[build-pyz]" && shiv -c curlcmd -o curlcmd.pyz .`.

> **Nota sobre antivírus.** Binários do PyInstaller às vezes disparam um falso
> positivo no Windows Defender/SmartScreen. Confira o SHA256 publicado, ou
> instale via `pipx`/`pip` se o seu ambiente bloqueia binários não assinados.
>
> **Recursos que dependem de Python.** O binário standalone **não** inclui
> Chromium/mitmproxy/payloads: validadores em navegador, proxy interceptador e
> download de wordlists exigem uma instalação via Python. Rode `curlcmd doctor`
> para o diagnóstico.

---

## 2. Primeiros passos: `setup` e `doctor`

Depois de instalar, use o `setup` para habilitar recursos opcionais e o `doctor`
para diagnosticar tudo. Ambos são idempotentes, falam português e nunca baixam
nada em silêncio — mostram o plano e pedem confirmação (ou `--yes` em scripts).

```bash
curlcmd setup            # confere a base e mostra os recursos opcionais
curlcmd setup --all      # instala todos os recursos opcionais e as fontes de payloads
curlcmd setup --browser  # só os validadores em navegador (Playwright + Chromium)
curlcmd setup --proxy    # só o proxy interceptador (mitmproxy)
curlcmd doctor           # diagnostica a instalação; com --fix instala o que faltar
```

`curlcmd --version` mostra a versão **e** como o curlcmd foi instalado.
`curlcmd self-update` atualiza pelo método detectado (pipx/uv/pip). Extras também
podem ser instalados à mão: `pip install "curlcommander[browser]"` +
`playwright install chromium`, `"[proxy]"`, `"[socks]"`, `"[clipboard]"`.

---

## 3. Segurança

Esta é a seção mais importante — o banco de histórico guarda metadados das
requisições e, sem cuidado, isso vira um despejo de credenciais de clientes.

**O que é redigido (padrão).** Antes de qualquer coisa ser escrita no histórico,
no export JSON, nos arquivos de evidência ou nos logs, os segredos são removidos:

- Valores de auth Bearer/Basic/API-key, `Authorization`/`Proxy-Authorization`,
  `Cookie`/`Set-Cookie`, `X-API-Key` e cabeçalhos afins, e credenciais de proxy.
- Segredos vindos de `--env-file` são guardados como **referências resolvíveis**
  (`{{VAR}}`), para poderem ser repetidos depois; o resto do que é secreto vira
  `«REDACTED»` e é de fato descartado.
- O `curl` armazenado é regenerado a partir da requisição já redigida, então
  nunca vaza.

**O que não é redigido.** Método, caminho da URL, hostnames, cabeçalhos não
sensíveis, parâmetros de query e corpos são guardados como estão (um segredo
embutido direto numa query ou corpo é responsabilidade sua). `--no-redact`
desliga a redação por completo e imprime um aviso.

**Revelar.** `curlcmd history --reveal`, `curlcmd curl <id> --reveal` e
`export-history --reveal` resolvem as referências `{{VAR}}` do ambiente atual.
Valores `«REDACTED»` são irrecuperáveis por design.

**Local de armazenamento.** O histórico fica no diretório de dados do SO —
`%LOCALAPPDATA%\CurlCommander` (Windows), `~/Library/Application Support/CurlCommander`
(macOS), `~/.local/share/curlcommander` (Linux, respeita `XDG_DATA_HOME`). Defina
`CURLCOMMANDER_HOME` para sobrescrever (uso portátil/CI). Um `~/.curlcommander`
legado de versões antigas é migrado automaticamente na primeira execução.

**Permissões de arquivo.** O diretório é criado com `0700` e o `history.db` com
`0600` (cookie jars de sessão `0600`) em sistemas POSIX. **No Windows** o `chmod`
só alterna o bit somente-leitura — não restringe outros usuários locais — então
no Windows a proteção real do histórico é a **redação de segredos** (ligada por
padrão); não a desligue com `--no-redact` numa máquina compartilhada.

**Segurança operacional para pentests.** `--scope scope.txt` recusa qualquer
alvo fora da allowlist. `--dry-run` mostra os bytes exatos sem enviar.
`--no-verify` sempre imprime um aviso visível. `--evidence DIR --engagement
LABEL` salva requisição + resposta cruas + metadados para o relatório.

Uma linha prefixada com `!` no `scope.txt` **exclui** um host, mesmo que ele
também bata com um wildcard mais amplo na allowlist — a exclusão sempre vence
sobre o allow, não importa a ordem das linhas no arquivo. Útil quando um
subdomínio específico (staging, um painel de terceiro, etc.) está sob o mesmo
wildcard do alvo mas não deve nunca ser tocado:

```text
# scope.txt
*.karwei.nl
!horrenconfigurator.karwei.nl
```

---

## 4. CLI

```bash
curlcmd https://httpbin.org/get                         # GET simples
curlcmd -X POST --json '{"name":"ada"}' https://api/x   # POST JSON
curlcmd --auth-bearer $TOKEN -H "Accept: application/json" https://api/me
curlcmd -H "X-Forwarded-For: 1.1.1.1" -H "X-Forwarded-For: 2.2.2.2" https://x  # cabeçalhos duplicados
curlcmd -p "id=1" -p "id=2" https://x                   # HPP (parâmetros duplicados)
curlcmd -X POST -F "file=@shell.php;type=image/png" https://x/upload
curlcmd --curl-only -X POST --json '{"id":1}' https://api/x   # só imprime o curl
```

### Fluxo AppSec: DevTools → importar → editar → reenviar → validar

```bash
# 1. "Copy as cURL" no DevTools/Burp, importar e reenviar pelo Burp:
curlcmd --import 'curl "https://api.x/me" -H "Cookie: s=abc" --data-raw "{}"' --burp

# 2. Importar um bloco cru do Burp Repeater, redirecionado a outro host:
curlcmd --import-raw request.txt --host https://staging.target

# 3. Validar uma correção em CI (código 3 na falha, junit para o pipeline):
curlcmd --assert-status 200 --assert-header "X-Frame-Options: DENY" \
        --assert-jsonpath '$.user.id==42' --assert-max-ms 500 \
        --report junit https://api.x/me
```

### Fuzzing

```bash
curlcmd -w words.txt "https://x/FUZZ" --mc 200,301 --fs 0 --concurrency 20 --rate 10
curlcmd --payloads sqli "https://x/item?id=FUZZ" --mr "SQL syntax"
curlcmd -w users.txt -w pass.txt --fuzz-mode pitchfork "https://x/FUZZ1:FUZZ2"
curlcmd --payloads traversal --encode url,url "https://x/file?p=FUZZ"   # url dupla
```

### Auth macro (login automático + renovação de sessão)

Uma macro de login (JSON/YAML) autentica sozinha e renova a sessão quando ela
expira no meio de um fuzz — renovação *single-flight* (uma rajada de 401
dispara **um** login só). Aplica-se a requisições únicas, `discover` e
`bounty-scan`. Mutuamente exclusiva com `--auth-bearer/--auth-basic/--auth-apikey`.

```bash
curlcmd --auth-macro login.json "https://api/me"
curlcmd discover https://t -w seclists:... --auth-macro login.json
# apps que devolvem 200 com HTML de "sessão expirada":
curlcmd --auth-macro login.json --session-die-regex "sess.o expirada" "https://api/me"
```

```json
{
  "backend": "http",
  "request": {"method": "POST", "url": "https://api/login",
              "body_type": "json", "body": "{\"user\":\"{{USER}}\",\"pass\":\"{{PASS}}\"}"},
  "extract": {"token": {"json": "$.access_token"}},
  "apply": {"header": "Authorization", "template": "Bearer {token}"},
  "ttl_seconds": 3600,
  "die": {"status": [401, 403]}
}
```

`backend: "browser"` faz o login num Chromium real (extra `[browser]`) para
casos com JS/CSRF, capturando cookies HttpOnly via Playwright. `{{USER}}`/`{{PASS}}`
resolvem das variáveis de ambiente. JSONPath rico é opcional (extra `[auth]`).

### Controle cru / pentest

```bash
curlcmd --raw-path "https://x/a/../../etc/passwd"        # caminho enviado byte a byte
curlcmd --no-default-headers -H "Host: internal" https://x
curlcmd --raw-request smuggle.txt --host https://target  # CL.TE/TE.CL, byte a byte
curlcmd --scope scope.txt --evidence out/ --engagement ENG-2026-07 https://x/y
```

### Estilos de API

```bash
curlcmd --graphql '{ me { id } }' https://x/graphql
curlcmd --graphql-introspection https://x/graphql        # reporta se habilitado
curlcmd --soap @envelope.xml --soap-action "urn:Login" https://x/svc
curlcmd --stream https://x/events                        # NDJSON / SSE
```

### WebSocket (extra `[ws]`)

O mesmo motor de fuzz (clusterbomb/pitchfork, filtros, anomalia) roda sobre
WebSocket — só o transporte muda. `connect` abre uma sessão interativa; `fuzz`
troca o marcador `FUZZ` na mensagem-molde por cada payload, uma resposta por
envio.

```bash
curlcmd ws connect wss://alvo/socket
curlcmd ws fuzz wss://alvo/socket --message '{"cmd":"FUZZ"}' -w payloads.txt --mr '"error"'
```

### Histórico

```bash
curlcmd history [--reveal]        # listar (redigido por padrão)
curlcmd replay <id>              # reenviar (resolve {{VAR}} do ambiente)
curlcmd curl <id> [--reveal]     # imprimir o curl armazenado
curlcmd export-history -o h.json [--reveal]
curlcmd delete-history <id>
curlcmd clear-history
```

### Importar coleções (OpenAPI / Postman)

Carrega um spec inteiro no histórico como requisições reenviáveis. Onde o spec
não traz exemplo, o campo vira um marcador `FUZZ` — pronto para o fuzzer. Cada
requisição fica etiquetada com sua proveniência (`origin`, ex.: `openapi:api.yaml`).

```bash
curlcmd import openapi api.yaml --out colecao.json          # OpenAPI 3.0/3.1
curlcmd import postman collection.json --env env.json       # resolve {{var}} do ambiente
curlcmd history                                             # veja o que foi importado
```

> `securitySchemes` (bearer/basic/apiKey) viram `auth_type`/`auth_value`; segredos
> resolvidos de um ambiente Postman são redigidos antes de tocar o histórico.

### Manutenção da instalação

```bash
curlcmd setup [--all|--browser|--proxy|--socks|--clipboard] [--payloads] [--yes]
curlcmd doctor [--fix]
curlcmd self-update [--yes]
```

### Flags

| Flag | Descrição |
|------|-----------|
| `-X, --method` | Método HTTP (qualquer token; não validado) |
| `-H, --header` | Cabeçalho `Chave: Valor` (repetível, duplicatas preservadas) |
| `-p, --param` | Parâmetro de query `chave=valor` (repetível, capaz de HPP) |
| `-b, --body` / `--body-file` | Corpo cru / corpo a partir de arquivo |
| `--json` / `--form` | Corpo JSON / form-urlencoded |
| `--auth-bearer` / `--auth-basic` / `--auth-apikey` | Autenticação |
| `--cookie` / `--cookie-jar` / `--session` | Cookies e sessões nomeadas |
| `-F, --form-file` | Campo/arquivo multipart `nome=@caminho[;type=;filename=]` |
| `--proxy` | URL de proxy (`http://127.0.0.1:8080`) |
| `--retry` / `--retry-delay` / `--compressed` / `--http2` | Transporte |
| `--output` | Salva os bytes crus da resposta num arquivo |
| `--raw` / `--pretty` | Desliga / força a formatação de exibição |
| `--env-file` | Carrega substituições `{{VAR}}` de um arquivo |
| `--no-redirect` / `--no-verify` / `--timeout` | Opções da requisição |
| `--fail` | Sai com 22 em HTTP ≥ 400 |
| `--no-redact` / `--reveal` | Controles de redação de segredos |
| `--import` / `--import-file` / `--import-clipboard` | Importar curl |
| `--import-raw` / `--host` | Importar um bloco HTTP cru |
| `--assert-status/-header/-body-contains/-jsonpath/-max-ms` | Asserções |
| `--report json\|junit` | Relatório de asserções |
| `-w, --wordlist` / `--payloads` | Wordlist de fuzz / payloads embutidos |
| `--fuzz-mode` / `--encode` / `--concurrency` / `--rate` | Controle de fuzz |
| `--mc/--fc/--ms/--fs/--mr` | Match/filtro de fuzz (código/tamanho/regex) |
| `--raw-path` / `--raw-request` / `--no-default-headers` | Controle cru |
| `--graphql[-vars/-introspection]` / `--xml` / `--soap[-action/-envelope]` | Estilos de API |
| `--grpc-web` / `--stream` | gRPC-web / streaming |
| `--scope` / `--dry-run` / `--evidence` / `--engagement` | Segurança operacional |
| `--log-file` / `--log-level` | Logging redigido |
| `--curl-only` / `--save` / `--gui` / `--version` | Diversos |

Códigos de saída: `0` ok · `1` uso/parse · `2` rede/DNS/TLS/timeout ·
`3` asserção falhou · `22` HTTP ≥ 400 com `--fail`.

---

## 5. Interface no terminal (TUI)

```bash
curlcmd --gui
```

A TUI é organizada em abas (um "Burp na TUI"):

- **Requisição** — painel de requisição (método/URL/cabeçalhos/parâmetros/corpo/
  auth **e** opções: proxy, timeout, retentativas, verificação, redirects,
  HTTP/2, compressed, cookies), curl gerado ao vivo, resposta em abas (Body /
  Headers / Raw / Cookies) com busca, e a tabela de histórico.
- **Repeater** — cada requisição vira uma sub-aba persistente com editor raw
  livre, reenvio, e histórico de reenvios empilhado para comparar tentativas.
- **Intruder** — marca posições de ataque (`§…§`), escolhe um dos 4 modos
  (Sniper / Battering ram / Pitchfork / Cluster bomb) e vê a grade de resultados
  ordenável, com anomalias destacadas. Promove uma linha para o Repeater.
- **Proxy** — inicia o proxy interceptador (extra `[proxy]`), lista o tráfego
  capturado ao vivo (fora do escopo fica esmaecido, não some) e envia qualquer
  captura para o Repeater ou o Intruder.
- **Validar** — formulário sobre os validadores (`xss`/`cors`/`open-redirect`/
  `clickjacking`/`csrf`/`ssrf`/`idor`), campos específicos por categoria,
  cores de veredito iguais às da CLI (CONFIRMED vermelho, REFLECTED amarelo,
  NOT_VULNERABLE verde) e persistência automática do achado.
- **Recon** — árvore domínio → subdomínios → URLs vivas → achados do nuclei
  por severidade, atualizada ao vivo conforme o pipeline
  subfinder→httpx→nuclei roda; Enter/clique numa URL promove para o Repeater.
- **Achados** — tabela ao vivo dos achados persistidos do engajamento ativo,
  agrupável por severidade, com botão **Gerar relatório** (chama `core.report`
  e abre o HTML resultante).
- **WebSocket** — conecta, envia mensagens e mostra enviado/recebido em duas
  colunas (extra `[ws]`).

Um rodapé fixo (barra de status) permite definir o **engajamento**, o
**arquivo de escopo** e a **macro de login** ativos uma vez — como o
`--config` da CLI (seção 8.1), toda aba lê esse mesmo estado em vez de
carregar sua própria cópia dos três campos.

O visualizador de resposta das abas novas tem Pretty/Raw/Headers/Cookies, busca
com contagem navegável ("2/7"), diff entre reenvios e o botão **Analisar**
(análise passiva de segurança: headers, cookies, CORS, erros → candidatos).

| Tecla | Ação |
|-------|------|
| `Ctrl+S` | Enviar (portátil; `Ctrl+Enter` também funciona onde o terminal suporta) |
| `Ctrl+R` | Enviar a requisição atual para o Repeater · `Ctrl+I` para o Intruder |
| `Ctrl+Y` | Copiar o curl gerado para a área de transferência |
| `Ctrl+X` | Cancelar a requisição em andamento |
| `Ctrl+L` | Limpar formulário · `Ctrl+H` Histórico · `Ctrl+Q` Sair |

Os atalhos aparecem no rodapé (Footer) da tela; há também um botão **Sair**
visível. Referências `{{VAR}}` no formulário são resolvidas do ambiente ao enviar.

---

## 6. Armazenamento do histórico

As requisições são guardadas no diretório de dados do SO (veja "Local de
armazenamento" acima) como `history.db` (SQLite, `0600` em POSIX). A requisição
completa é mantida como um snapshot `config_json` redigido, então a repetição é
sem perdas; upgrades de esquema rodam automaticamente via `PRAGMA user_version`.

**Isolamento por engajamento.** Sem `--engagement`, tudo cai no `history.db`
compartilhado (uso ad-hoc). Com `--engagement NOME` — em qualquer comando que já
aceita a flag (requisição normal, `validate`, `bounty-scan`, `proxy`, `report`,
`history`/`replay`/`curl`/`export-history`/`delete-history`/`clear-history`) —
histórico **e** achados persistidos ficam isolados em
`<diretório de dados>/engagements/NOME/history.db`, um arquivo por cliente/
engajamento. Isso é confidencialidade, não só organização: ao final de um
engajamento, dá pra apagar os dados de um cliente específico sem tocar em
nenhum outro.

```bash
curlcmd engagement list                    # engajamentos isolados + contagem de registros
curlcmd engagement delete cliente-x        # apaga histórico + achados desse engajamento inteiro
```

> `engagement delete` só apaga o `history.db` isolado (histórico + achados). Se
> você também usou `--evidence CAMINHO` apontando pra outro lugar, aquele
> diretório não é tocado — ele foi escolhido por você e pode não ser exclusivo
> deste engajamento.

**Arquivo de config do engajamento (`--config`).** Repetir `--engagement`/
`--scope`/`--auth-macro`/`--proxy` em toda invocação (durante um engajamento
que pode durar semanas) convida a erro de digitação — e como `--engagement`
é uma string livre casada por igualdade exata, um typo cria silenciosamente
um segundo engajamento, sem aviso. Um arquivo TOML lido uma vez resolve isso:

```toml
# engajamento.toml
[engagement]
name = "cliente-x"
scope_file = "scope-cliente-x.txt"
auth_macro = "login-cliente-x.yaml"
proxy = "http://127.0.0.1:8080"

[wordlists]
default_source = "seclists"   # documentado; ainda não aplicado automaticamente
```

```bash
curlcmd --config engajamento.toml "https://api.cliente-x.com/x"
curlcmd report --config engajamento.toml --out relatorio.html
```

`--config` só preenche o que você **não** digitou nesta chamada — qualquer
`--engagement`/`--scope`/`--auth-macro`/`--proxy` explícito na linha de
comando sempre vence sobre o arquivo, não importa a posição de `--config` em
`argv`. Disponível em toda a superfície que já aceita essas flags (requisição
normal, `discover`, `bounty-scan`, `validate`, `proxy`, `report`,
`history`/`replay`/`curl`/`export-history`/`delete-history`/`clear-history`).

---

## 7. Bug bounty — payloads → fuzz → discover

As fontes de payloads (SecLists, PayloadsAllTheThings, FuzzDB) são sincronizadas
sob demanda, não embutidas. Aponte para um checkout existente com `SECLISTS_PATH`
/ `CURLCOMMANDER_PAYLOADS` em vez de sincronizar.

```bash
curlcmd payloads sync seclists          # clone raso e esparso no diretório de dados
curlcmd payloads list                    # categorias + fontes sincronizadas
curlcmd payloads search common           # encontra arquivos de wordlist
curlcmd payloads show xss --count        # dimensiona uma rodada de fuzz

# Resolva por intenção ou por caminho de origem — um só motor de fuzz, os mesmos filtros:
curlcmd --payloads xss "https://t/s?q=FUZZ" --mr "alert\("
curlcmd -w seclists:Discovery/Web-Content/common.txt "https://t/FUZZ" --fc 404
curlcmd --payloads-all sqli --encode url "https://t/i?id=FUZZ"   # todas as fontes, deduplicado

# Descoberta de conteúdo (dirbusting) e um perfil encadeado:
curlcmd discover https://t -w seclists:Discovery/Web-Content/raft-medium-directories.txt -e php,bak --recurse 1
curlcmd bounty-scan https://t/page --engagement ENG-2026 --categories xss,sqli,traversal
```

O `bounty-scan` consolida anomalias em **candidatos a investigar** ordenados por
severidade — nunca confirmações. Confirme-os num navegador (abaixo).

## 8. Validação por navegador e proxy interceptador

Dependências pesadas são extras opcionais que degradam com uma mensagem clara
(instale com `curlcmd setup --browser` / `--proxy`):

```bash
pip install "curlcommander[browser]" && playwright install chromium   # validadores
pip install "curlcommander[proxy]"                                     # proxy
```

O **validate** move um candidato refletido para CONFIRMADO executando-o num
navegador real (canário único por teste → sem falsos positivos). Toda navegação
é checada contra o escopo e exige `--engagement`.

```bash
curlcmd validate xss "https://t/s?q=§PAYLOAD§" --engagement ENG --evidence out/
curlcmd validate clickjacking https://t/panel --engagement ENG
curlcmd validate cors https://api.t/data --origin https://evil.example --engagement ENG
curlcmd validate open-redirect "https://t/r?next=§DEST§" --engagement ENG
```

`--evidence DIR` salva um screenshot, o DOM, um HAR e um trace do Playwright.

**Validação autenticada.** CORS anônimo quase nunca é explorável — o cenário
de impacto real é o mesmo bug atrás de login. `--cookie k=v` (repetível),
`--auth-bearer TOKEN` e `-H`/`--header` (repetível) valem para os cinco kinds
HTTP/navegador (`cors`, `open-redirect`, `xss`, `clickjacking`, `csrf`): em
`cors`/`open-redirect` entram nos cabeçalhos da requisição HTTP; nos
validadores de navegador o cookie é injetado no contexto do Playwright antes
de framear/enviar o formulário/navegar, e os cabeçalhos extras valem pro
contexto inteiro:

```bash
curlcmd validate cors https://api.t/data --origin https://evil.example \
  --cookie session=abc123 --auth-bearer $TOKEN --engagement ENG
curlcmd validate clickjacking https://t/painel-admin --cookie session=abc123 --engagement ENG
```

**SSRF cega via out-of-band** (extra `[oob]`): confirma SSRF/XXE/RCE cegos —
efeitos que não aparecem na resposta HTTP — fazendo o alvo conectar num host que
você controla (protocolo Interactsh: RSA-2048 + AES-256-CFB). DNS-only e conexão
HTTP completa são achados distintos.

```bash
curlcmd validate ssrf "https://t/fetch?url=FUZZ_OOB" --engagement ENG --i-understand-oob
curlcmd validate ssrf "https://t/fetch" --param url --interactsh-server oob.meu-lab.com --engagement ENG
```

> Metadados de conexão do alvo trafegam pelo servidor Interactsh. Use
> `--interactsh-server` com infraestrutura própria em cliente real; o servidor
> público exige `--i-understand-oob`. A URL de callback **não** é o alvo.

**IDOR / BOLA por correlação de autorização.** A mesma URL responde diferente
dependendo de **quem** autentica? Para cada `RESOURCE_ID`, a requisição é enviada
como a identidade A (dono baseline) e como B (atacante) — só a auth muda — e os
corpos são comparados. B recebendo `200` estruturalmente igual ao de A é
**confirmado**; `401/403/404` é **bloqueado**; o meio-termo vira **suspeito**
(exige análise humana). `--fuzz-range` mede quantos recursos B alcança de fato.

```bash
curlcmd validate idor "https://api/orders/RESOURCE_ID" --ids 101,102,103 \
        --auth-a dono.json --auth-b atacante.json --engagement ENG
curlcmd validate idor "https://api/orders/RESOURCE_ID" --ids 101 \
        --auth-a dono.json --auth-b atacante.json --fuzz-range 1000-1050 --engagement ENG
```

**Relatório de engajamento.** Todo `validate … --engagement ENG` grava o achado
validado; candidatos de `bounty-scan --engagement ENG` também são persistidos
(nunca como confirmação) e qualquer requisição normal com `--engagement ENG`
fica registrada no histórico do engajamento. `report` agrega tudo isso num
HTML único, agrupado por severidade (achados confirmados), com uma seção à
parte para não conclusivos/candidatos e um apêndice com as requisições
enviadas — reprodução (`curl`), evidência e remediação. Tudo derivado do alvo
é redigido (URL, headers, cookies **e** o conteúdo livre de `evidence`, como
uma requisição crua capturada via Interactsh) antes de tocar o disco, não só
no HTML — pronto para compartilhar.

```bash
curlcmd report --engagement ENG --out report.html
```

**Recon (subfinder/httpx/nuclei/katana).** O curlcmd cobre bem "já tenho uma
URL, quero atacar" — a fase anterior (enumeração de superfície) é orquestrada
via os binários reais do ProjectDiscovery, nunca reimplementados em Python:
detectados no `PATH` (`curlcmd doctor` sinaliza presença/ausência; **não são
instalados pelo curlcmd**, é `go install ...` manual), executados via
`asyncio.create_subprocess_exec` (nunca uma string de shell) e streamados como
JSON/JSONL linha a linha — nunca scraping de texto. Escopo é aplicado *antes*
de qualquer coisa tocar a rede: `subfinder`/`katana` recusam um alvo único fora
do escopo (mesmo "recusa dura" de `validate`/`proxy`); `httpx`/`nuclei` filtram
a lista de hosts/URLs *antes* de repassar pro binário — um host fora do escopo
nunca chega a ser sondado, só descartado e contado.

```bash
curlcmd recon subfinder -d alvo.com --scope scope.txt --out subs.jsonl
curlcmd recon httpx -l subs.txt --scope scope.txt --out vivos.jsonl
curlcmd recon nuclei -l urls.txt --severity medium,high,critical --scope scope.txt
curlcmd recon katana -u https://alvo.com --scope scope.txt --out crawl.jsonl
```

> Se o pacote Python `httpx` (o cliente HTTP, não relacionado) também expõe um
> executável `httpx` no seu `PATH`, ele pode colidir com o `httpx` do
> ProjectDiscovery — o curlcmd resolve pelo `PATH` (`shutil.which`), então
> confira `curlcmd doctor` se o probe se comportar de forma inesperada.

O **proxy** — um proxy HTTPS interceptador com CA própria, match-and-replace e
captura no histórico limitada ao escopo:

```bash
curlcmd proxy --ca                       # imprime o caminho da CA + guia de instalação/remoção
curlcmd proxy --port 8080 --scope scope.txt --engagement ENG \
        --replace 'resp:secret==>«X»' --launch-browser
```

> **Aviso da CA.** Instalar a CA do proxy no seu SO/navegador deixa ela
> descriptografar o seu TLS — confie nela só para testes e **remova depois**. Só
> hosts em escopo são interceptados; o resto é tunelado sem inspeção. O binário
> standalone **não** inclui Chromium/mitmproxy — instale os extras à parte para
> o modo navegador/proxy.

---

## 9. Desenvolvimento

```bash
uv pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest --cov=curlcommander
```

O `core/` nunca importa de `cli/` ou `gui/`. Veja o [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## 10. Roadmap

- Diffing de respostas entre entradas do histórico (`diff`), corpos armazenados.
- Timing detalhado (DNS/connect/TLS/TTFB) e visão da cadeia de redirects.
- Testes de vuln assistidos (heurísticas de reflexão, OAST), matrizes de
  bypass de auth/IDOR.
- mTLS (`--cert/--key/--cacert`), `--resolve`, `--unix-socket`, pinning.
- Export para Postman/coleções, coleções de requisições e ambientes.

## Changelog

Veja o [CHANGELOG.md](https://github.com/Ivomsantiago/Curl_Commander/blob/main/CHANGELOG.md) para todas as versões e histórico de mudanças.
