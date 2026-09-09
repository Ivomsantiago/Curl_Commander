"""Tests for OAuth2 / OIDC manager and PKCE generation."""

import pytest
import respx
from httpx import Response

from curlcommander.core.auth_oauth2 import OAuth2Manager, generate_pkce_pair
from curlcommander.core.request_model import RequestConfig


def test_pkce_generation():
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(challenge) >= 43
    assert verifier != challenge


@pytest.mark.asyncio
async def test_client_credentials_flow(respx_mock):
    respx_mock.post("https://auth.example.com/oauth/token").mock(
        return_value=Response(
            200,
            json={
                "access_token": "test-access-token-123",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "test-refresh-token-456",
            },
        )
    )

    manager = OAuth2Manager(
        token_url="https://auth.example.com/oauth/token",
        client_id="my-client",
        client_secret="my-secret",
    )

    token = await manager.get_token()
    assert token.access_token == "test-access-token-123"
    assert token.token_type == "Bearer"
    assert not token.is_expired

    cfg = RequestConfig(method="GET", url="https://api.example.com/data")
    updated = manager.apply_to_request(cfg, token)
    assert updated.headers["Authorization"] == "Bearer test-access-token-123"
