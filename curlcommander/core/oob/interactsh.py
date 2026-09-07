"""Interactsh client for out-of-band (OOB) interaction confirmation.

Blind SSRF/XXE/RCE have no observable effect in the HTTP response — the only
way to confirm them is to make the target open a network connection to a host
you control and observe it. This implements the real protocol of
projectdiscovery/interactsh: register an RSA public key, hand out per-payload
subdomains, poll for AES-encrypted interactions, decrypt them, and deregister.

``cryptography`` is an optional dependency (``oob`` extra); it is imported
lazily so the rest of the tool works without it.

Layout note: each poll ``data`` entry is base64 → ``IV(16) || ciphertext``
decrypted with AES-256-CFB using the poll's RSA-OAEP(SHA-256)-wrapped ``aes_key``.
This mirrors the reference client; a self-hosted server can be pointed at with
``server=``.
"""

from __future__ import annotations

import asyncio
import base64
import json
import secrets
import string
import uuid
from dataclasses import dataclass, field
from typing import Any

from curlcommander.core.request_model import RequestConfig

_DEFAULT_SERVER = "oast.pro"
_POLL_INTERVAL = 5.0


class OOBError(RuntimeError):
    pass


def oob_available() -> bool:
    try:
        import cryptography  # noqa: F401

        return True
    except Exception:
        return False


def require_oob() -> None:
    if not oob_available():
        from curlcommander.core import features

        raise OOBError(features.missing_message("oob"))


@dataclass
class Interaction:
    protocol: str  # dns | http | smtp | ldap
    unique_id: str  # full subdomain that was hit
    remote_address: str = ""
    raw_request: str = ""
    timestamp: str = ""


@dataclass
class InteractshClient:
    """A registered Interactsh session. Use :meth:`register` to start."""

    server: str = _DEFAULT_SERVER
    verify_ssl: bool = True
    correlation_id: str = ""
    secret_key: str = ""
    _private_key: Any = field(default=None, repr=False)
    _registered: bool = False
    _labels: dict[str, str] = field(default_factory=dict)  # label -> subdomain

    # -- lifecycle --------------------------------------------------------

    async def register(self) -> None:
        require_oob()
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        self._private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pub_pem = self._private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.correlation_id = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(20))
        self.secret_key = str(uuid.uuid4())

        body = json.dumps(
            {
                "public-key": base64.b64encode(pub_pem).decode(),
                "secret-key": self.secret_key,
                "correlation-id": self.correlation_id,
            }
        )
        result = await self._post("register", body)
        if result.error or (result.status_code and result.status_code >= 400):
            raise OOBError(f"registro no Interactsh falhou: {result.error or result.status_code}")
        self._registered = True

    async def deregister(self) -> None:
        """Free the correlation id on the server (best-effort)."""
        if not self._registered:
            return
        body = json.dumps({"correlation-id": self.correlation_id, "secret-key": self.secret_key})
        try:
            await self._post("deregister", body)
        except OOBError:
            pass
        self._registered = False

    # -- payloads ---------------------------------------------------------

    def new_payload_url(self, label: str = "") -> str:
        """A fresh callback subdomain, correlated to ``label`` for this test.

        The extra random prefix is what lets you tell WHICH fuzz payload caused
        WHICH interaction when dozens run in parallel.
        """
        if not self._registered:
            raise OOBError("chame register() antes de gerar URLs de callback")
        prefix = secrets.token_hex(8)
        subdomain = f"{prefix}.{self.correlation_id}.{self.server}"
        if label:
            self._labels[label] = subdomain
        return subdomain

    # -- polling ----------------------------------------------------------

    async def poll(self) -> list[Interaction]:
        """One poll cycle: fetch, decrypt and parse pending interactions."""
        require_oob()
        result = await self._get(f"poll?id={self.correlation_id}&secret={self.secret_key}")
        if result.error or not result.body:
            return []
        try:
            payload = json.loads(result.body)
        except json.JSONDecodeError:
            return []
        data = payload.get("data") or []
        aes_b64 = payload.get("aes_key")
        if not data or not aes_b64:
            return []
        aes_key = self._decrypt_aes_key(base64.b64decode(aes_b64))
        out: list[Interaction] = []
        for entry in data:
            try:
                obj = json.loads(self._decrypt_entry(aes_key, base64.b64decode(entry)))
            except Exception:
                continue
            out.append(
                Interaction(
                    protocol=str(obj.get("protocol", "")),
                    unique_id=str(obj.get("unique-id", "") or obj.get("full-id", "")),
                    remote_address=str(obj.get("remote-address", "")),
                    raw_request=str(obj.get("raw-request", "")),
                    timestamp=str(obj.get("timestamp", "")),
                )
            )
        return out

    async def wait_for(self, label: str, timeout: float = 15.0, interval: float = _POLL_INTERVAL) -> list[Interaction]:
        """Poll until interactions matching ``label``'s subdomain arrive, or timeout."""
        subdomain = self._labels.get(label, "")
        deadline = asyncio.get_event_loop().time() + timeout
        seen: list[Interaction] = []
        while asyncio.get_event_loop().time() < deadline:
            for it in await self.poll():
                if not subdomain or subdomain in it.unique_id:
                    seen.append(it)
            if seen:
                return seen
            await asyncio.sleep(interval)
        return seen

    # -- crypto -----------------------------------------------------------

    def _decrypt_aes_key(self, ciphertext: bytes) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        return self._private_key.decrypt(  # type: ignore[no-any-return]
            ciphertext,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )

    @staticmethod
    def _decrypt_entry(aes_key: bytes, blob: bytes) -> str:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        iv, ct = blob[:16], blob[16:]
        dec = Cipher(algorithms.AES(aes_key), modes.CFB(iv)).decryptor()
        plaintext: bytes = dec.update(ct) + dec.finalize()
        return plaintext.decode("utf-8", errors="replace")

    # -- transport (injectable for tests) --------------------------------

    def _url(self, path: str) -> str:
        return f"https://{self.server}/{path}"

    async def _post(self, path: str, body: str) -> Any:
        from curlcommander.core.http_client import send

        cfg = RequestConfig(method="POST", url=self._url(path), body=body, body_type="json", verify_ssl=self.verify_ssl)
        return await send(cfg)

    async def _get(self, path: str) -> Any:
        from curlcommander.core.http_client import send

        return await send(RequestConfig(method="GET", url=self._url(path), verify_ssl=self.verify_ssl))
