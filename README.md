# CurlCommander

**🌐 Idioma:** **Português** · [English](README.en.md)

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green.svg)](LICENSE)
[![CI](https://github.com/Ivomsantiago/Curl_Commander/actions/workflows/ci.yml/badge.svg)](https://github.com/Ivomsantiago/Curl_Commander/actions/workflows/ci.yml)
[![Releases](https://img.shields.io/github/v/release/Ivomsantiago/Curl_Commander?display_name=tag&sort=semver)](https://github.com/Ivomsantiago/Curl_Commander/releases)

Construtor de requisições HTTP no terminal, gerador de `curl` e ferramenta de
testes de API/AppSec. Monte e repita requisições, gere um `curl` fiel, importe
do DevTools ou do Burp, faça fuzzing, valide asserções e dispare requisições
byte a byte — tudo por um único ponto de entrada: `curlcmd`.

Feito para analistas e engenheiros que precisam de requisições confiáveis o
bastante para colar num relatório de pentest, expressivas o bastante para testar
qualquer estilo de API (REST, GraphQL, SOAP/XML, gRPC-web, formulários legados)
e programáveis o bastante para rodar em CI.

Python 3.11+ · `httpx` · `rich` · `prompt_toolkit` · `textual`.

![Demonstração do CurlCommander](docs/demo.gif)

> _O arquivo `docs/demo.gif` é um espaço reservado para a demonstração animada
> da ferramenta. Substitua-o por uma gravação real do `curlcmd` em uso._

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

### Histórico

```bash
curlcmd history [--reveal]        # listar (redigido por padrão)
curlcmd replay <id>              # reenviar (resolve {{VAR}} do ambiente)
curlcmd curl <id> [--reveal]     # imprimir o curl armazenado
curlcmd export-history -o h.json [--reveal]
curlcmd delete-history <id>
curlcmd clear-history
```

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
