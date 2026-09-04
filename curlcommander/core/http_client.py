import asyncio
import time

import httpx

from curlcommander.core.auth_handler import resolve_auth
from curlcommander.core.cookies import load_jar, save_jar, session_jar_path
from curlcommander.core.multipart import build_multipart
from curlcommander.core.request_model import RequestConfig, ResponseResult
from curlcommander.core.response_formatter import decode_body


def _resolve_jar_path(config: RequestConfig) -> str:
    if config.session:
        return str(session_jar_path(config.session))
    return config.cookie_jar or ""


async def send(config: RequestConfig) -> ResponseResult:
    resolved = resolve_auth(config)

    auth: tuple[str, str] | None = None
    if config.auth_type == "basic" and ":" in config.auth_value:
        username, password = config.auth_value.split(":", 1)
        auth = (username, password)

    # Multipart upload takes precedence over a raw body when -F specs exist.
    multipart_data: dict[str, str] | None = None
    multipart_files: list | None = None
    if resolved.form:
        multipart_data, multipart_files = build_multipart(resolved.form)

    content: bytes | None = None
    if resolved.body and not resolved.form:
        content = resolved.body.encode()
        if resolved.body_type == "json" and "Content-Type" not in resolved.headers:
            resolved.headers["Content-Type"] = "application/json"
        elif resolved.body_type == "form" and "Content-Type" not in resolved.headers:
            resolved.headers["Content-Type"] = "application/x-www-form-urlencoded"

    if resolved.compressed and "Accept-Encoding" not in resolved.headers:
        resolved.headers["Accept-Encoding"] = "gzip, deflate, br"

    # Cookie jar / session handling.
    jar_path = _resolve_jar_path(resolved)
    cookies = load_jar(jar_path) if jar_path else httpx.Cookies()
    for name, value in resolved.cookies:
        cookies.set(name, value)

    start = time.perf_counter()

    proxy = None
    if resolved.proxy:
        proxy = resolved.proxy

    attempt = 0
    while True:
        try:
            async with httpx.AsyncClient(
                verify=resolved.verify_ssl,
                follow_redirects=resolved.follow_redirects,
                timeout=resolved.timeout,
                http2=resolved.http2,
                proxy=proxy,
                cookies=cookies,
            ) as client:
                response = await client.request(
                    method=resolved.method,
                    url=resolved.url,
                    headers=resolved.headers.as_tuples(),
                    params=resolved.params.as_tuples(),
                    content=content,
                    data=multipart_data,
                    files=multipart_files,
                    auth=auth,
                )
                if jar_path:
                    save_jar(jar_path, client.cookies)

            elapsed_ms = (time.perf_counter() - start) * 1000
            content_type = response.headers.get("content-type", "")
            return ResponseResult(
                status_code=response.status_code,
                reason=response.reason_phrase,
                headers=dict(response.headers),
                body=decode_body(response.content, content_type),
                content_type=content_type,
                duration_ms=elapsed_ms,
                size_bytes=len(response.content),
                error=None,
                content=response.content,
            )
        except httpx.RequestError as exc:
            attempt += 1
            if attempt > resolved.max_retries:
                elapsed_ms = (time.perf_counter() - start) * 1000
                return ResponseResult(
                    status_code=None,
                    reason="",
                    headers={},
                    body="",
                    content_type="",
                    duration_ms=elapsed_ms,
                    size_bytes=0,
                    error=str(exc),
                )
            if resolved.retry_delay > 0:
                await asyncio.sleep(resolved.retry_delay)
            continue
