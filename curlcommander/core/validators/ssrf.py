"""Blind SSRF confirmation via an out-of-band callback (item 2.4).

Injects a unique Interactsh callback URL into the target request and waits for
the target to reach out. A full HTTP connection and a DNS-only resolution are
*different findings* (a firewalled target that resolves but cannot connect is
not the same as one that fetches the URL) and are reported distinctly, never
collapsed into a single "SSRF confirmed".
"""

from __future__ import annotations

from curlcommander.core.fuzzer import substitute
from curlcommander.core.http_client import send
from curlcommander.core.oob.interactsh import Interaction, InteractshClient
from curlcommander.core.request_model import RequestConfig
from curlcommander.core.validators.base import CONFIRMED, ERROR, NOT_VULNERABLE, ValidationResult

_MARKER = "FUZZ_OOB"


async def validate_ssrf(
    url: str,
    client: InteractshClient,
    param: str = "",
    verify_ssl: bool = True,
    timeout: float = 30.0,
    wait_timeout: float = 15.0,
) -> ValidationResult:
    """Inject a per-test OOB URL, fire the request, wait for the callback."""
    subdomain = client.new_payload_url(label="ssrf")
    callback = f"http://{subdomain}/"

    if _MARKER in url:
        base = substitute(
            RequestConfig(method="GET", url=url, verify_ssl=verify_ssl, timeout=timeout), {_MARKER: callback}
        )
    else:
        base = RequestConfig(method="GET", url=url, verify_ssl=verify_ssl, timeout=timeout)
        if param:
            base.params.set(param, callback)
        else:
            base.url = url.rstrip("/") + "/" + callback  # last resort: append

    result = await send(base)
    if result.error:
        return ValidationResult("ssrf", ERROR, url, detail=result.error, payload=callback)

    interactions = await client.wait_for("ssrf", timeout=wait_timeout)
    return _verdict(url, callback, interactions)


def _verdict(url: str, callback: str, interactions: list[Interaction]) -> ValidationResult:
    http_hits = [i for i in interactions if i.protocol == "http"]
    dns_hits = [i for i in interactions if i.protocol == "dns"]

    if http_hits:
        it = http_hits[0]
        return ValidationResult(
            "ssrf",
            CONFIRMED,
            url,
            detail="SSRF confirmado: o alvo abriu uma conexão HTTP completa para o callback OOB.",
            payload=callback,
            evidence={
                "protocol": "http",
                "remote_address": it.remote_address,
                "raw_request": it.raw_request,
                "timestamp": it.timestamp,
                "unique_id": it.unique_id,
            },
        )
    if dns_hits:
        it = dns_hits[0]
        return ValidationResult(
            "ssrf",
            CONFIRMED,
            url,
            detail=(
                "SSRF cega (apenas DNS): o alvo RESOLVEU o host do callback mas não conectou. "
                "Impacto/severidade menores que uma conexão HTTP completa — investigar filtragem de saída."
            ),
            payload=callback,
            evidence={
                "protocol": "dns",
                "remote_address": it.remote_address,
                "timestamp": it.timestamp,
                "unique_id": it.unique_id,
            },
        )
    return ValidationResult(
        "ssrf",
        NOT_VULNERABLE,
        url,
        detail="Nenhuma interação OOB no tempo de espera (não confirma; pode ser assíncrono/lento).",
        payload=callback,
    )
