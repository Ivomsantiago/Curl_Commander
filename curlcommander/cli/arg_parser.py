import argparse
from typing import NoReturn


def _version() -> str:
    from curlcommander import __version__

    return __version__


def _version_line() -> str:
    """Version plus how curlcmd was installed (PT-BR), for ``--version``."""
    from curlcommander.core import features

    return f"curlcmd {_version()} (instalação: {features.install_method()})"


class ArgParser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 1 (usage error) instead of 2."""

    def error(self, message: str) -> NoReturn:
        self.print_usage()
        self.exit(1, f"{self.prog}: error: {message}\n")


def build_request_parser() -> argparse.ArgumentParser:
    """Parser used when no subcommand is detected (request / wizard mode)."""
    parser = ArgParser(
        prog="curlcmd",
        description="CurlCommander — construtor de requisições HTTP e gerador de curl",
    )
    parser.add_argument("url", nargs="?", help="URL de destino")
    imp = parser.add_argument_group("importação")
    imp.add_argument("--import", dest="import_curl", metavar="CURL", help="Importa um comando curl (string)")
    imp.add_argument("--import-file", metavar="CAMINHO", help="Importa um comando curl de um arquivo")
    imp.add_argument("--import-clipboard", action="store_true", help="Importa um comando curl da área de transferência")
    imp.add_argument("--import-raw", metavar="CAMINHO", help="Importa um bloco HTTP cru (Burp/.http)")
    imp.add_argument("--host", metavar="URL", help="Host base para --import-raw / --raw-request (ex.: https://alvo)")

    api = parser.add_argument_group("estilos de API")
    api.add_argument("--graphql", metavar="QUERY", help="Envia uma query GraphQL (POST JSON)")
    api.add_argument("--graphql-vars", metavar="JSON", help="Variáveis GraphQL em JSON")
    api.add_argument(
        "--graphql-introspection", action="store_true", help="Envia query de introspection e reporta se habilitada"
    )
    api.add_argument("--xml", metavar="CORPO|@ARQ", help="Envia um corpo XML (application/xml)")
    api.add_argument("--soap", metavar="CORPO|@ARQ", help="Envia um corpo SOAP/XML (text/xml)")
    api.add_argument("--soap-action", metavar="URI", help="Valor do cabeçalho SOAPAction")
    api.add_argument("--soap-envelope", action="store_true", help="Embrulha o corpo --soap num envelope SOAP")
    api.add_argument("--grpc-web", action="store_true", help="Define content-type gRPC-web (use --body-file p/ bytes)")
    api.add_argument("--stream", action="store_true", help="Faz streaming da resposta linha a linha (NDJSON/SSE)")

    raw = parser.add_argument_group("controle cru / pentest")
    raw.add_argument("--raw-request", metavar="CAMINHO", help="Envia um bloco HTTP cru byte a byte por um socket")
    raw.add_argument("--no-fix-length", action="store_true", help="Nunca recalcula Content-Length p/ --raw-request")
    raw.add_argument("--raw-path", action="store_true", help="Envia o caminho da URL byte a byte (sem normalização)")
    raw.add_argument(
        "--no-default-headers", action="store_true", help="Não envia os cabeçalhos padrão do httpx (UA/Accept/...)"
    )

    opsec = parser.add_argument_group("segurança operacional")
    opsec.add_argument("--scope", metavar="CAMINHO", help="Allowlist de hosts/CIDRs em escopo; recusa fora do escopo")
    opsec.add_argument("--dry-run", action="store_true", help="Mostra o que seria enviado na rede, sem enviar")
    opsec.add_argument("--evidence", metavar="DIR", help="Salva requisição+resposta+metadados crus em DIR")
    opsec.add_argument("--engagement", metavar="LABEL", help="Rótulo de autorização/engajamento p/ evidência")

    fuzz = parser.add_argument_group("fuzzing")
    fuzz.add_argument(
        "-w",
        "--wordlist",
        action="append",
        dest="wordlists",
        default=[],
        metavar="CAMINHO",
        help="Wordlist para marcadores FUZZ (repetível)",
    )
    fuzz.add_argument(
        "--payloads",
        action="append",
        dest="payloads",
        default=[],
        metavar="CAT",
        help="Categoria de payload via catálogo (xss/sqli/ssti/lfi/ssrf/...)",
    )
    fuzz.add_argument(
        "--payloads-all",
        action="append",
        dest="payloads_all",
        default=[],
        metavar="CAT",
        help="Categoria de payload de TODAS as fontes sincronizadas, deduplicado",
    )
    fuzz.add_argument(
        "--fuzz-mode", choices=["clusterbomb", "pitchfork"], default="clusterbomb", help="Modo multi-wordlist"
    )
    fuzz.add_argument("--encode", metavar="LISTA", help="Cadeia de encoders aplicada aos payloads (ex.: url,base64)")
    fuzz.add_argument("--concurrency", type=int, default=10, metavar="N", help="Requisições de fuzz concorrentes")
    fuzz.add_argument(
        "--rate", type=float, default=0.0, metavar="R", help="Máx. requisições por segundo (0 = ilimitado)"
    )
    fuzz.add_argument("--mc", metavar="CODES", help="Casa códigos de status (separados por vírgula)")
    fuzz.add_argument("--fc", metavar="CODES", help="Filtra códigos de status (separados por vírgula)")
    fuzz.add_argument("--ms", type=int, metavar="N", help="Casa resposta de N bytes")
    fuzz.add_argument("--fs", type=int, metavar="N", help="Filtra resposta de N bytes")
    fuzz.add_argument("--mr", metavar="REGEX", help="Casa regex no corpo")
    parser.add_argument("-X", "--method", default="GET", metavar="MÉTODO", help="Método HTTP (padrão: GET)")
    parser.add_argument(
        "-H",
        "--header",
        action="append",
        dest="headers",
        default=[],
        metavar="Chave: Valor",
        help="Cabeçalho (repetível)",
    )
    parser.add_argument(
        "-p",
        "--param",
        action="append",
        dest="params",
        default=[],
        metavar="chave=valor",
        help="Parâmetro de query (repetível)",
    )
    parser.add_argument("-b", "--body", default="", help="Corpo da requisição (string)")
    parser.add_argument("--body-file", metavar="CAMINHO", help="Lê o corpo da requisição de um arquivo")
    parser.add_argument("--json", dest="json_body", metavar="JSON", help="Corpo JSON (define o Content-Type sozinho)")
    parser.add_argument("--form", dest="form_body", metavar="DADOS", help="Corpo form-urlencoded")
    parser.add_argument("--auth-bearer", metavar="TOKEN", help="Token Bearer")
    parser.add_argument("--auth-basic", metavar="USUÁRIO:SENHA", help="Credenciais Basic auth")
    parser.add_argument("--auth-apikey", metavar="'Cabeçalho: Valor'", help="Auth por API key")
    parser.add_argument(
        "--cookie", action="append", dest="cookies", default=[], metavar="k=v", help="Cookie (repetível)"
    )
    parser.add_argument("--cookie-jar", metavar="CAMINHO", help="Persiste/carrega cookies num arquivo jar")
    parser.add_argument("--session", metavar="NOME", help="Sessão nomeada (cookie jar persistente)")
    parser.add_argument(
        "-F",
        "--form-file",
        action="append",
        dest="form",
        default=[],
        metavar="nome=@arquivo",
        help="Campo/arquivo multipart (repetível)",
    )
    parser.add_argument("--proxy", metavar="URL", help="URL de proxy para rotear a requisição")
    parser.add_argument("--burp", action="store_true", help="Atalho para --proxy http://127.0.0.1:8080 --no-verify")
    parser.add_argument("--retry", type=int, default=0, metavar="N", help="Tentativas de repetição em erro de rede")
    parser.add_argument("--retry-delay", type=float, default=0.0, metavar="SEGUNDOS", help="Espera entre tentativas")
    parser.add_argument("--compressed", action="store_true", help="Pede resposta comprimida")
    parser.add_argument("--http2", action="store_true", help="Usa HTTP/2 se suportado")
    parser.add_argument("--output", metavar="CAMINHO", default="", help="Salva o corpo da resposta num arquivo")
    parser.add_argument("--pretty", action="store_true", help="Formata o corpo (JSON já é formatado por padrão)")
    parser.add_argument("--raw", action="store_true", help="Desativa a formatação da resposta")
    parser.add_argument("--env-file", metavar="CAMINHO", help="Carrega variáveis de ambiente p/ substituições")
    parser.add_argument("--no-redirect", action="store_true", help="Não segue redirects")
    parser.add_argument("--no-verify", action="store_true", help="Desativa a verificação do certificado SSL")
    parser.add_argument(
        "--timeout", type=float, default=30.0, metavar="SEGUNDOS", help="Timeout da requisição (padrão: 30)"
    )
    asserts = parser.add_argument_group("asserções (modo de teste)")
    asserts.add_argument("--assert-status", type=int, metavar="N", help="Afirma que o status HTTP é igual a N")
    asserts.add_argument(
        "--assert-header",
        action="append",
        dest="assert_headers",
        default=[],
        metavar="Nome: Valor",
        help="Afirma cabeçalho (repetível)",
    )
    asserts.add_argument(
        "--assert-body-contains",
        action="append",
        dest="assert_body",
        default=[],
        metavar="STR",
        help="Afirma que o corpo contém STR (repetível)",
    )
    asserts.add_argument(
        "--assert-jsonpath",
        action="append",
        dest="assert_jsonpath",
        default=[],
        metavar="EXPR",
        help="Afirma JSONPath (ex.: '$.user.id==42')",
    )
    asserts.add_argument("--assert-max-ms", type=float, metavar="MS", help="Afirma tempo de resposta abaixo de MS ms")
    asserts.add_argument("--report", choices=["json", "junit"], help="Emite um relatório de asserções no stdout")

    parser.add_argument(
        "--no-redact", action="store_true", help="Guarda credenciais em texto claro no histórico (inseguro)"
    )
    parser.add_argument("--fail", action="store_true", help="Sai com 22 em status HTTP >= 400 (como curl --fail)")
    parser.add_argument("--curl-only", action="store_true", help="Imprime o comando curl sem enviar")
    parser.add_argument("--save", action="store_true", help="Salva no histórico mesmo com --curl-only")
    parser.add_argument("--gui", action="store_true", help="Abre a TUI (Textual)")
    parser.add_argument("--log-file", metavar="CAMINHO", help="Escreve logs estruturados e redigidos em CAMINHO")
    parser.add_argument("--log-level", choices=["debug", "info", "warning", "error"], help="Verbosidade do log")
    parser.add_argument("--version", action="version", version=_version_line())
    return parser


def build_subcommand_parser() -> argparse.ArgumentParser:
    """Parser used when a subcommand (history, replay, curl, clear-history) is detected."""
    parser = ArgParser(
        prog="curlcmd",
        description="CurlCommander — subcomandos",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    history_p = subparsers.add_parser("history", help="Lista o histórico de requisições")
    history_p.add_argument("--reveal", action="store_true", help="Resolve as referências de segredo {{VAR}}")

    replay_p = subparsers.add_parser("replay", help="Repete uma entrada do histórico pelo ID")
    replay_p.add_argument("id", type=int, help="ID da entrada do histórico")

    curl_p = subparsers.add_parser("curl", help="Imprime o curl de uma entrada do histórico")
    curl_p.add_argument("id", type=int, help="ID da entrada do histórico")
    curl_p.add_argument("--reveal", action="store_true", help="Resolve as referências de segredo {{VAR}}")

    export_p = subparsers.add_parser("export-history", help="Exporta o histórico para JSON")
    export_p.add_argument("-o", "--output", default="history.json", metavar="CAMINHO", help="Caminho do arquivo JSON")
    export_p.add_argument("--reveal", action="store_true", help="Resolve as referências de segredo {{VAR}}")

    delete_p = subparsers.add_parser("delete-history", help="Apaga uma entrada do histórico pelo ID")
    delete_p.add_argument("id", type=int, help="ID da entrada do histórico")

    subparsers.add_parser("clear-history", help="Limpa todo o histórico")

    # setup (install optional extras + payloads; PT-BR, idempotent)
    setup_p = subparsers.add_parser("setup", help="Instalar recursos opcionais (navegador/proxy/socks/payloads)")
    setup_p.add_argument("--all", action="store_true", help="Instalar todos os recursos opcionais e payloads")
    setup_p.add_argument("--browser", action="store_true", help="Validadores em navegador (Playwright)")
    setup_p.add_argument("--proxy", action="store_true", help="Proxy interceptador (mitmproxy)")
    setup_p.add_argument("--socks", action="store_true", help="Suporte a proxy SOCKS")
    setup_p.add_argument("--clipboard", action="store_true", help="Área de transferência (pyperclip)")
    setup_p.add_argument("--payloads", action="store_true", help="Baixar/atualizar as fontes de payloads")
    setup_p.add_argument("-y", "--yes", action="store_true", help="Não perguntar; assumir sim (uso em scripts/CI)")

    # doctor (diagnose install; --fix installs what it can)
    doctor_p = subparsers.add_parser("doctor", help="Diagnosticar a instalação e recursos opcionais")
    doctor_p.add_argument("--fix", action="store_true", help="Tentar instalar/corrigir o que estiver faltando")
    doctor_p.add_argument("-y", "--yes", action="store_true", help="Não perguntar durante o --fix (scripts/CI)")

    # self-update (update curlcmd via the detected install method)
    selfup_p = subparsers.add_parser("self-update", help="Atualizar o curlcmd pelo método de instalação detectado")
    selfup_p.add_argument("-y", "--yes", action="store_true", help="Rodar a atualização sem perguntar")

    # payloads sync / update / list / search / show
    payloads_p = subparsers.add_parser("payloads", help="Gerencia fontes de payloads e o catálogo")
    p_sub = payloads_p.add_subparsers(dest="payloads_cmd", required=True)
    p_sync = p_sub.add_parser("sync", help="Clona/atualiza uma fonte de payloads")
    p_sync.add_argument("source", nargs="?", help="Nome da fonte (padrão: todas)")
    p_sub.add_parser("update", help="Atualiza todas as fontes sincronizadas")
    p_list = p_sub.add_parser("list", help="Lista categorias do catálogo / fontes sincronizadas")
    p_list.add_argument("--category", metavar="CAT", help="Lista os arquivos que compõem uma categoria")
    p_search = p_sub.add_parser("search", help="Busca por nomes de arquivos de wordlist")
    p_search.add_argument("term", help="Trecho a buscar")
    p_show = p_sub.add_parser("show", help="Prévia dos payloads de uma categoria")
    p_show.add_argument("category", help="Nome da categoria")
    p_show.add_argument("--limit", type=int, default=20, help="Máx. de linhas a mostrar")
    p_show.add_argument("--count", action="store_true", help="Imprime só o total")
    p_show.add_argument("--all", action="store_true", dest="all_sources", help="Usa todas as fontes sincronizadas")

    # discover (content discovery via the fuzz engine)
    disc = subparsers.add_parser("discover", help="Descoberta de conteúdo / dirbusting contra uma URL")
    disc.add_argument("url", help="URL base")
    disc.add_argument("-w", "--wordlist", action="append", dest="wordlists", default=[], metavar="SPEC")
    disc.add_argument("--payloads", action="append", dest="payloads", default=[], metavar="CAT")
    disc.add_argument("-e", "--extensions", metavar="EXT", help="Comma-separated extensions (php,bak,old)")
    disc.add_argument("--recurse", type=int, default=0, metavar="DEPTH", help="Shallow recursion depth")
    disc.add_argument("--concurrency", type=int, default=20, metavar="N")
    disc.add_argument("--rate", type=float, default=0.0, metavar="R")
    disc.add_argument("--mc", metavar="CODES")
    disc.add_argument("--fc", metavar="CODES", default="404")
    disc.add_argument("--ms", type=int, metavar="N")
    disc.add_argument("--fs", type=int, metavar="N")
    disc.add_argument("--mr", metavar="REGEX")
    disc.add_argument("--scope", metavar="PATH")
    disc.add_argument("--no-verify", action="store_true")
    disc.add_argument("--timeout", type=float, default=30.0)

    # proxy (intercepting HTTPS proxy with its own CA)
    prox = subparsers.add_parser("proxy", help="Roda um proxy HTTPS interceptador (mitmproxy)")
    prox.add_argument("--port", type=int, default=8080)
    prox.add_argument("--scope", metavar="CAMINHO", help="Intercepta só hosts em escopo; tunela o resto")
    prox.add_argument("--engagement", metavar="LABEL", help="Rótulo de autorização (obrigatório)")
    prox.add_argument(
        "--replace",
        action="append",
        dest="replace",
        default=[],
        metavar="REGRA",
        help="Match-and-replace: [req|resp:]padrão==>substituição (repetível)",
    )
    prox.add_argument("--launch-browser", action="store_true", help="Abre o Chromium roteado pelo proxy")
    prox.add_argument("--ca", action="store_true", help="Imprime o caminho da CA + guia de instalação/remoção e sai")

    # validate (browser-executed / HTTP vulnerability validators)
    val = subparsers.add_parser("validate", help="Valida uma vulnerabilidade (navegador/HTTP)")
    val.add_argument("kind", choices=["xss", "cors", "open-redirect", "clickjacking", "csrf"])
    val.add_argument("url", help="URL alvo (use marcadores §PAYLOAD§/§DEST§ onde couber)")
    val.add_argument("--engagement", metavar="LABEL", help="Rótulo de autorização (obrigatório)")
    val.add_argument("--scope", metavar="CAMINHO")
    val.add_argument("--origin", metavar="ORIGEM", default="https://evil.example", help="Origem atacante p/ CORS")
    val.add_argument("--headed", action="store_true", help="Mostra a janela do navegador")
    val.add_argument("--evidence", metavar="DIR", help="Salva screenshot/DOM/HAR aqui")
    val.add_argument("--no-verify", action="store_true")
    val.add_argument("--timeout", type=float, default=30.0)

    # bounty-scan (discover + per-category fuzz, consolidated by severity)
    bounty = subparsers.add_parser("bounty-scan", help="Perfil encadeado de discovery + fuzz de payloads")
    bounty.add_argument("url", help="URL alvo")
    bounty.add_argument("--scope", metavar="CAMINHO")
    bounty.add_argument("--engagement", metavar="LABEL", help="Rótulo de autorização (obrigatório)")
    bounty.add_argument("--categories", metavar="LIST", default="xss,sqli,traversal,ssti")
    bounty.add_argument("--concurrency", type=int, default=10)
    bounty.add_argument("--rate", type=float, default=0.0)
    bounty.add_argument("--no-verify", action="store_true")
    bounty.add_argument("--timeout", type=float, default=30.0)

    return parser


SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "history",
        "replay",
        "curl",
        "export-history",
        "delete-history",
        "clear-history",
        "setup",
        "doctor",
        "self-update",
        "payloads",
        "discover",
        "bounty-scan",
        "validate",
        "proxy",
    }
)
