"""OAuth2 / OIDC authentication flows and automatic token management.

Supports:
- Client Credentials Grant
- Resource Owner Password Credentials Grant
- Authorization Code Grant with PKCE (S256)
- Refresh Token Grant
- Token caching with automatic expiration tracking
"""

from __future__ import annotations

import base64
import hashlib
import os
import time
from dataclasses import dataclass

import httpx

from curlcommander.core.request_model import RequestConfig


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE (code_verifier, code_challenge) pair using SHA-256 (S256)."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
    challenge_bytes = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(challenge_bytes).decode("ascii").rstrip("=")
    return verifier, challenge


@dataclass
class OAuth2Token:
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    refresh_token: str | None = None
    scope: str | None = None
    acquired_at: float = 0.0

    @property
    def is_expired(self) -> bool:
        if self.expires_in <= 0:
            return False
        # Buffer of 10 seconds before actual expiration
        return (time.time() - self.acquired_at) >= (self.expires_in - 10)


class OAuth2Manager:
    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str | None = None,
        grant_type: str = "client_credentials",
        scope: str | None = None,
    ) -> None:
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.grant_type = grant_type
        self.scope = scope
        self._cached_token: OAuth2Token | None = None

    async def get_token(
        self,
        username: str | None = None,
        password: str | None = None,
        code: str | None = None,
        redirect_uri: str | None = None,
        code_verifier: str | None = None,
        force_refresh: bool = False,
    ) -> OAuth2Token:
        if not force_refresh and self._cached_token and not self._cached_token.is_expired:
            return self._cached_token

        if self._cached_token and self._cached_token.refresh_token:
            try:
                token = await self.refresh(self._cached_token.refresh_token)
                self._cached_token = token
                return token
            except Exception:
                pass  # Fallback to full flow if refresh fails

        payload: dict[str, str] = {
            "grant_type": self.grant_type,
            "client_id": self.client_id,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret
        if self.scope:
            payload["scope"] = self.scope

        if self.grant_type == "password":
            if username:
                payload["username"] = username
            if password:
                payload["password"] = password
        elif self.grant_type == "authorization_code":
            if code:
                payload["code"] = code
            if redirect_uri:
                payload["redirect_uri"] = redirect_uri
            if code_verifier:
                payload["code_verifier"] = code_verifier

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_url, data=payload)
            resp.raise_for_status()
            data = resp.json()

        token = OAuth2Token(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=int(data.get("expires_in", 3600)),
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope"),
            acquired_at=time.time(),
        )
        self._cached_token = token
        return token

    async def refresh(self, refresh_token: str) -> OAuth2Token:
        payload: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_url, data=payload)
            resp.raise_for_status()
            data = resp.json()

        return OAuth2Token(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=int(data.get("expires_in", 3600)),
            refresh_token=data.get("refresh_token", refresh_token),
            scope=data.get("scope"),
            acquired_at=time.time(),
        )

    def apply_to_request(self, config: RequestConfig, token: OAuth2Token) -> RequestConfig:
        cloned = RequestConfig.from_dict(config.to_dict())
        cloned.headers["Authorization"] = f"{token.token_type} {token.access_token}"
        return cloned
