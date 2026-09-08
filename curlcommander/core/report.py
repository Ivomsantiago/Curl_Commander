"""Engagement report builder (item 6): validated findings -> single HTML.

Aggregates every persisted :class:`ValidationResult` for an engagement (which
now also includes bounty-scan candidates, see ``core.validators.base.CANDIDATE``)
plus the plain request :class:`HistoryEntry` rows fired under it, groups
findings by severity, and renders one self-contained HTML file (inline CSS, no
external assets). Each finding carries a description, endpoint, severity, an
explanation, the payload, copy-paste repro (a ``curl`` built from the endpoint),
the captured evidence, and remediation guidance.

Everything user/target-derived is redacted (``redaction.redact_config`` /
``redact_evidence``) and HTML-escaped before it enters the document, so a
report is safe to share.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

from curlcommander.core.curl_builder import build_curl
from curlcommander.core.discovery import severity_of
from curlcommander.core.redaction import redact_config, redact_evidence, redact_url_query
from curlcommander.core.request_model import HistoryEntry, RequestConfig
from curlcommander.storage.validation_repo import StoredValidation

_EXPLANATION = {
    "xss": "Entrada refletida/armazenada é executada como script no navegador da vítima.",
    "ssrf": "O servidor pode ser induzido a fazer requisições para destinos escolhidos pelo atacante.",
    "idor": "O mesmo endpoint devolve recursos de outra identidade — falha de autorização (BOLA).",
    "cors": "A política CORS permite que uma origem não confiável leia respostas autenticadas.",
    "csrf": "Uma ação sensível pode ser disparada a partir de outra origem sem token anti-CSRF.",
    "clickjacking": "A página pode ser embutida em um iframe e sobreposta para enganar o clique do usuário.",
    "open-redirect": "Um parâmetro controla o destino de redirecionamento, útil para phishing/OAuth.",
}

_REMEDIATION = {
    "xss": "Escape/encode a saída por contexto e aplique uma CSP restritiva.",
    "ssrf": "Valide e restrinja destinos por allowlist; bloqueie IPs internos e metadados de nuvem.",
    "idor": "Verifique a autorização por objeto no servidor para cada requisição, não só a autenticação.",
    "cors": "Reflita apenas origens confiáveis; nunca combine `Access-Control-Allow-Origin: *` com credenciais.",
    "csrf": "Exija tokens anti-CSRF e/ou cookies `SameSite` em ações que mudam estado.",
    "clickjacking": "Defina `X-Frame-Options: DENY` ou `Content-Security-Policy: frame-ancestors 'none'`.",
    "open-redirect": "Use allowlist de destinos ou caminhos relativos; nunca redirecione para URL crua do usuário.",
}

_SEVERITY_ORDER = ("high", "medium", "low")
_SEVERITY_LABEL = {"high": "Alta", "medium": "Média", "low": "Baixa"}


@dataclass
class Finding:
    category: str
    severity: str
    verdict: str
    url: str
    detail: str
    payload: str
    curl: str
    evidence: dict[str, object]


def report_severity(category: str, evidence: dict[str, object] | None = None) -> str:
    """Severity for a finding: ``discovery.severity_of`` is the single source
    of truth for the category, but a validator may know its OWN instance is
    weaker or stronger than the category default (e.g. SSRF that only
    resolved DNS vs. one that opened a full HTTP connection) and say so via
    an explicit ``evidence["severity"]`` override.
    """
    if evidence:
        override = evidence.get("severity")
        if override in _SEVERITY_ORDER:
            return str(override)
    return severity_of(category)


def _to_finding(sv: StoredValidation) -> Finding:
    r = sv.result
    safe = redact_config(RequestConfig(method="GET", url=redact_url_query(r.url)), {})
    # Defense in depth: evidence is already redacted at persistence time
    # (cli/runner.py::_persist_validation), but the report re-applies it in
    # case a row ever reaches here through another path.
    evidence = redact_evidence(dict(r.evidence))
    return Finding(
        category=r.category,
        severity=report_severity(r.category, evidence),
        verdict=r.verdict,
        url=safe.url,
        detail=r.detail,
        payload=r.payload,
        curl=build_curl(safe),
        evidence=evidence,
    )


def build_report(
    engagement: str,
    stored: list[StoredValidation],
    history: list[HistoryEntry] | None = None,
) -> str:
    """Render the full HTML report for an engagement.

    ``stored`` covers every persisted :class:`ValidationResult` — validator
    findings AND bounty-scan candidates (verdict ``CANDIDATE``, which lands in
    the non-conclusive section below, matching bounty-scan's own "candidates
    to investigate, never confirmations" stance). ``history`` is the plain
    request log for the engagement (``--engagement`` on a normal request),
    included as an appendix so the report also shows everything that was
    touched, not just what triggered a finding.
    """
    confirmed = [_to_finding(s) for s in stored if s.result.verdict == "CONFIRMED"]
    others = [_to_finding(s) for s in stored if s.result.verdict != "CONFIRMED"]

    buckets: dict[str, list[Finding]] = {s: [] for s in _SEVERITY_ORDER}
    for f in confirmed:
        buckets.setdefault(f.severity, []).append(f)

    parts: list[str] = [_HEAD, _header(engagement, confirmed, others)]
    if not confirmed:
        parts.append("<p class='empty'>Nenhum achado confirmado registrado para este engajamento.</p>")
    for sev in _SEVERITY_ORDER:
        items = buckets.get(sev, [])
        if not items:
            continue
        parts.append(f"<h2 class='sev sev-{sev}'>Severidade {_SEVERITY_LABEL[sev]} ({len(items)})</h2>")
        parts.extend(_finding_html(f, i + 1) for i, f in enumerate(items))
    if others:
        parts.append(_other_section(others))
    if history:
        parts.append(_history_section(history))
    parts.append(_FOOT)
    return "\n".join(parts)


def _header(engagement: str, confirmed: list[Finding], others: list[Finding]) -> str:
    e = html.escape(engagement)
    return (
        f"<h1>Relatório de engajamento — {e}</h1>"
        f"<p class='meta'>{len(confirmed)} achado(s) confirmado(s), "
        f"{len(others)} não conclusivo(s)/negativo(s).</p>"
        "<p class='meta warn'>Dados sensíveis foram redigidos. Distribua apenas com autorização.</p>"
    )


def _finding_html(f: Finding, index: int) -> str:
    cat = html.escape(f.category)
    rows = [
        f"<h3 class='sev-{f.severity}'>#{index} — {cat} <span class='badge'>{html.escape(f.verdict)}</span></h3>",
        _kv("Endpoint", f"<code>{html.escape(f.url)}</code>"),
        _kv("Severidade", _SEVERITY_LABEL.get(f.severity, f.severity)),
        _kv("Descrição", html.escape(f.detail) if f.detail else "—"),
        _kv("Explicação", html.escape(_EXPLANATION.get(f.category, "—"))),
    ]
    if f.payload:
        rows.append(_kv("Payload", f"<code>{html.escape(f.payload)}</code>"))
    rows.append(_kv("Reprodução", f"<pre>{html.escape(f.curl)}</pre>"))
    if f.evidence:
        ev = "".join(f"<li><b>{html.escape(str(k))}:</b> {html.escape(str(v))}</li>" for k, v in f.evidence.items())
        rows.append(_kv("Evidência", f"<ul class='ev'>{ev}</ul>"))
    rows.append(_kv("Remediação", html.escape(_REMEDIATION.get(f.category, "—"))))
    return f"<section class='finding'>{''.join(rows)}</section>"


def _other_section(others: list[Finding]) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(o.category)}</td><td>{html.escape(o.verdict)}</td>"
        f"<td><code>{html.escape(o.url)}</code></td><td>{html.escape(o.detail)}</td></tr>"
        for o in others
    )
    return (
        "<h2>Não conclusivos / negativos</h2>"
        "<table class='others'><thead><tr><th>Categoria</th><th>Veredito</th>"
        f"<th>Endpoint</th><th>Detalhe</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _history_section(history: list[HistoryEntry]) -> str:
    """Appendix: every plain request fired under the engagement, findings or not.

    Rows already went through `redact_config` at persistence time (unless the
    analyst ran with `--no-redact`); this re-redacts as defense in depth so
    the report never depends on that having happened correctly upstream.
    """
    rows = []
    for e in history:
        safe = redact_config(e.request, {})
        status = str(e.status_code) if e.status_code is not None else "—"
        rows.append(
            f"<tr><td>{html.escape(e.timestamp)}</td><td>{html.escape(e.request.method)}</td>"
            f"<td><code>{html.escape(redact_url_query(safe.url))}</code></td><td>{status}</td></tr>"
        )
    return (
        f"<h2>Requisições do engajamento ({len(history)})</h2>"
        "<p class='meta'>Histórico completo enviado com este --engagement, não apenas os achados acima.</p>"
        "<table class='others'><thead><tr><th>Quando</th><th>Método</th>"
        f"<th>URL</th><th>Status</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _kv(key: str, value_html: str) -> str:
    return f"<div class='kv'><span class='k'>{html.escape(key)}</span><div class='v'>{value_html}</div></div>"


_HEAD = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório de engajamento — CurlCommander</title>
<style>
 body{font:14px/1.5 system-ui,sans-serif;margin:0;padding:2rem;background:#f6f7f9;color:#1c1e21}
 h1{margin:0 0 .25rem} .meta{color:#555;margin:.15rem 0} .meta.warn{color:#a5601a}
 .empty{padding:1rem;background:#fff;border-radius:8px}
 h2.sev{margin-top:2rem;padding:.3rem .6rem;border-radius:6px;color:#fff}
 .sev-high,h2.sev-high{background:#c0392b} .sev-medium,h2.sev-medium{background:#d68910}
 .sev-low,h2.sev-low{background:#2874a6}
 .finding{background:#fff;border-radius:8px;padding:1rem 1.25rem;margin:1rem 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}
 .finding h3{margin:.2rem 0 .8rem;border-bottom:2px solid #eee;padding-bottom:.4rem}
 .finding h3.sev-high{color:#c0392b} .finding h3.sev-medium{color:#d68910} .finding h3.sev-low{color:#2874a6}
 .badge{float:right;font-size:.75rem;background:#eee;color:#333;border-radius:4px;padding:.1rem .4rem}
 .kv{display:flex;gap:1rem;margin:.35rem 0} .kv .k{flex:0 0 8.5rem;color:#666;font-weight:600} .kv .v{flex:1;min-width:0}
 code{background:#f0f1f3;padding:.05rem .3rem;border-radius:4px;word-break:break-all}
 pre{background:#1e1e1e;color:#eee;padding:.7rem;border-radius:6px;overflow-x:auto;white-space:pre-wrap;word-break:break-all}
 ul.ev{margin:.2rem 0;padding-left:1.1rem} table.others{width:100%;border-collapse:collapse;background:#fff}
 table.others th,table.others td{border:1px solid #e2e4e8;padding:.4rem;text-align:left;font-size:.85rem}
</style></head><body>"""

_FOOT = "<p class='meta'>Gerado por CurlCommander.</p></body></html>"
