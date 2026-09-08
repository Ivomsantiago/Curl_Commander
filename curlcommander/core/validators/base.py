"""Shared types for browser-executed vulnerability validators (H.2/H.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Verdicts. CONFIRMED means the browser actually executed/triggered the issue,
# not merely that a payload reflected.
CONFIRMED = "CONFIRMED"
REFLECTED = "REFLECTED"
NOT_VULNERABLE = "NOT_VULNERABLE"
ERROR = "ERROR"
# A bounty-scan anomaly: a lead to investigate, never a confirmation (see
# core/discovery.py::BountyReport). Persisted as a ValidationResult so
# `curlcmd report` can aggregate it alongside real validator findings.
CANDIDATE = "CANDIDATE"


@dataclass
class ValidationResult:
    category: str
    verdict: str
    url: str
    detail: str = ""
    payload: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def confirmed(self) -> bool:
        return self.verdict == CONFIRMED
