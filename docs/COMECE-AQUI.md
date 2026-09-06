# Comece aqui — CurlCommander em 5 minutos

Guia rápido em português para instalar, conferir e disparar a primeira
requisição. Para a documentação completa, veja o [README](../README.md).

## 1. Instale

**Uma linha (recomendado):**

```bash
# Linux/macOS
curl -fsSL https://raw.githubusercontent.com/Ivomsantiago/Curl_Commander/main/scripts/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/Ivomsantiago/Curl_Commander/main/scripts/install.ps1 | iex
```

O instalador escolhe sozinho o melhor método (`uv` → `pipx` → venv gerenciado),
cria o atalho `curlcmd` e diz exatamente o que fazer se ele não estiver no PATH.

> Sem Python? Baixe o binário standalone na página de
> [Releases](https://github.com/Ivomsantiago/Curl_Commander/releases) e rode
> direto — mas note que navegador/proxy/payloads exigem uma instalação via Python.

## 2. Confira

```bash
curlcmd --version     # mostra a versão e como foi instalado
curlcmd doctor        # diagnostica a instalação e os recursos opcionais
```

Se o `doctor` apontar um ✗ essencial, ele já diz a correção. Os ○ amarelos são
recursos opcionais — normais de estarem ausentes numa instalação básica.

## 3. (Opcional) Habilite recursos

```bash
curlcmd setup            # confere a base e lista os recursos opcionais
curlcmd setup --browser  # validadores em navegador (Playwright + Chromium)
curlcmd setup --all      # tudo: navegador, proxy, socks, área de transferência e payloads
```

Nada é baixado em silêncio: o `setup` mostra o que vai instalar e pede
confirmação (use `--yes` em scripts).

## 4. Primeira requisição

```bash
curlcmd https://httpbin.org/get                       # GET simples
curlcmd -X POST --json '{"nome":"ada"}' https://httpbin.org/post
curlcmd --curl-only -X POST --json '{"id":1}' https://api.exemplo/x   # só o curl
```

Veja o histórico e repita uma requisição:

```bash
curlcmd history          # lista (segredos redigidos por padrão)
curlcmd replay 1         # reenvia a entrada #1
curlcmd curl 1           # imprime o curl armazenado
```

## 5. Próximos passos

- Fluxo AppSec (importar do DevTools/Burp, editar, reenviar, validar): README §4.
- Fuzzing e bug bounty (`payloads`, `discover`, `bounty-scan`): README §7.
- Validação por navegador e proxy interceptador: README §8.
- Segurança e redação de segredos (leia antes de usar em cliente): README §3.

Problemas? Rode `curlcmd doctor` primeiro — ele costuma apontar a causa e a
correção. Para atualizar depois: `curlcmd self-update`.
