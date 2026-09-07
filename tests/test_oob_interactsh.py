"""Tests for the Interactsh OOB client + SSRF validator (item 2)."""

import base64
import json
import os

import httpx
import pytest
import respx

from curlcommander.core.oob.interactsh import Interaction, InteractshClient, OOBError
from curlcommander.core.validators.base import CONFIRMED, NOT_VULNERABLE
from curlcommander.core.validators.ssrf import validate_ssrf


def _server_encrypt(pub_pem: bytes, interaction: dict) -> tuple[str, str]:
    """Simulate the Interactsh server side: AES-256-CFB the interaction, RSA-wrap the key."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    aes_key = os.urandom(32)
    iv = os.urandom(16)
    enc = Cipher(algorithms.AES(aes_key), modes.CFB(iv)).encryptor()
    ct = enc.update(json.dumps(interaction).encode()) + enc.finalize()
    data_entry = base64.b64encode(iv + ct).decode()

    pub = serialization.load_pem_public_key(pub_pem)
    wrapped = pub.encrypt(
        aes_key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    return data_entry, base64.b64encode(wrapped).decode()


@respx.mock
async def test_interactsh_crypto_roundtrip():
    pytest.importorskip("cryptography")  # the optional [oob] extra
    captured: dict[str, bytes] = {}

    def on_register(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured["pub"] = base64.b64decode(body["public-key"])
        assert len(body["correlation-id"]) == 20
        return httpx.Response(200, json={})

    respx.post("https://oast.pro/register").mock(side_effect=on_register)

    client = InteractshClient(server="oast.pro")
    await client.register()
    sub = client.new_payload_url("t1")
    assert sub.endswith(f".{client.correlation_id}.oast.pro")

    data_entry, aes_b64 = _server_encrypt(
        captured["pub"],
        {"protocol": "http", "unique-id": sub, "remote-address": "1.2.3.4", "raw-request": "GET /", "timestamp": "t"},
    )
    respx.get(url__regex=r"https://oast\.pro/poll.*").mock(
        return_value=httpx.Response(200, json={"data": [data_entry], "aes_key": aes_b64})
    )

    hits = await client.poll()
    assert len(hits) == 1
    assert hits[0].protocol == "http" and sub in hits[0].unique_id and hits[0].remote_address == "1.2.3.4"
    # wait_for correlates by the label's subdomain
    found = await client.wait_for("t1", timeout=1.0, interval=0.01)
    assert found and found[0].protocol == "http"


@respx.mock
async def test_register_unreachable_raises():
    pytest.importorskip("cryptography")  # the optional [oob] extra
    respx.post("https://oast.pro/register").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(OOBError):
        await InteractshClient().register()


def test_new_payload_url_requires_register():
    with pytest.raises(OOBError):
        InteractshClient().new_payload_url("x")


def _ready_client() -> InteractshClient:
    c = InteractshClient()
    c._registered = True
    c.correlation_id = "corr1234corr1234corr"
    return c


@respx.mock
async def test_validate_ssrf_http_is_confirmed(monkeypatch):
    respx.get(url__regex=r"https://t/.*").mock(return_value=httpx.Response(200, text="ok"))
    client = _ready_client()

    async def fake_wait(label, timeout=15.0, interval=5.0):
        return [Interaction(protocol="http", unique_id=client._labels["ssrf"], remote_address="9.9.9.9")]

    monkeypatch.setattr(client, "wait_for", fake_wait)
    res = await validate_ssrf("https://t/x?u=FUZZ_OOB", client)
    assert res.verdict == CONFIRMED and "HTTP" in res.detail
    assert res.evidence["protocol"] == "http"


@respx.mock
async def test_validate_ssrf_dns_only_is_distinct(monkeypatch):
    respx.get(url__regex=r"https://t/.*").mock(return_value=httpx.Response(200))
    client = _ready_client()

    async def fake_wait(label, timeout=15.0, interval=5.0):
        return [Interaction(protocol="dns", unique_id=client._labels["ssrf"])]

    monkeypatch.setattr(client, "wait_for", fake_wait)
    res = await validate_ssrf("https://t/x?u=FUZZ_OOB", client)
    assert res.verdict == CONFIRMED and "DNS" in res.detail  # not collapsed with HTTP


@respx.mock
async def test_validate_ssrf_no_interaction(monkeypatch):
    respx.get(url__regex=r"https://t/.*").mock(return_value=httpx.Response(200))
    client = _ready_client()

    async def fake_wait(label, timeout=15.0, interval=5.0):
        return []

    monkeypatch.setattr(client, "wait_for", fake_wait)
    res = await validate_ssrf("https://t/x?u=FUZZ_OOB", client)
    assert res.verdict == NOT_VULNERABLE


def test_ssrf_consent_gate_refuses_public_server_without_flag():
    from argparse import Namespace

    from curlcommander.cli import runner

    args = Namespace(
        kind="ssrf",
        url="https://t/x?u=FUZZ_OOB",
        engagement="ENG",
        scope=None,
        no_verify=False,
        timeout=30.0,
        param=None,
        interactsh_server=None,  # -> public default
        wait=15.0,
        i_understand_oob=False,
    )
    assert runner._run_ssrf(args, True, 30.0) == runner.EXIT_USAGE
