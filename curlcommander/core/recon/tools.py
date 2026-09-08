"""Detection and execution of external recon binaries (item 7).

CurlCommander covers "I already have a URL, let's attack it" (fuzz, discover,
intruder, proxy, validate) but nothing upstream of that — surface enumeration.
Reimplementing subfinder/httpx/nuclei/katana in Python would duplicate worse
versions of mature, purpose-built Go tools, so this module orchestrates the
real binaries instead: detect them on PATH (never installed/downloaded by
curlcmd itself — that stays a manual, explicit step for the user), run them
via ``asyncio.create_subprocess_exec`` (never a shell string), and stream
their JSON/JSONL stdout as structured records rather than scraping text.

Same optional-dependency shape as ``core.browser``/``core.proxy``: a lazy
availability check, a ``require_*`` that raises a clear, actionable message,
and callers that degrade instead of crashing when a tool is missing.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


class ReconToolError(RuntimeError):
    """Raised when a recon binary is required but not found on PATH."""


@dataclass(frozen=True)
class ReconTool:
    name: str  # doctor/CLI key, e.g. "subfinder"
    binary: str  # executable name looked up on PATH
    label: str  # human PT-BR label (curlcmd doctor)
    install_hint: str  # how a user gets it — not pip-installable, so manual


TOOLS: dict[str, ReconTool] = {
    "subfinder": ReconTool(
        name="subfinder",
        binary="subfinder",
        label="enumeração de subdomínios (subfinder)",
        install_hint="go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest",
    ),
    "httpx": ReconTool(
        name="httpx",
        binary="httpx",
        label="probe de hosts vivos (httpx-projectdiscovery)",
        install_hint="go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest",
    ),
    "nuclei": ReconTool(
        name="nuclei",
        binary="nuclei",
        label="templates de vulnerabilidade (nuclei)",
        install_hint="go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest",
    ),
    "katana": ReconTool(
        name="katana",
        binary="katana",
        label="crawler (katana)",
        install_hint="go install -v github.com/projectdiscovery/katana/cmd/katana@latest",
    ),
}


def tool_path(name: str) -> str | None:
    """Absolute path to the binary on PATH, or None if it isn't installed."""
    tool = TOOLS.get(name)
    if tool is None:
        return None
    return shutil.which(tool.binary)


def available(name: str) -> bool:
    return tool_path(name) is not None


def require(name: str) -> str:
    """Raise ReconToolError with an actionable message, else return the path."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ReconToolError(f"ferramenta de recon desconhecida: {name!r}")
    path = tool_path(name)
    if path is None:
        raise ReconToolError(f"{tool.label} não encontrado no PATH. Instale com:\n  {tool.install_hint}")
    return path


async def run_and_stream(name: str, args: list[str]) -> AsyncIterator[dict[str, Any]]:
    """Run a recon binary and yield each JSON/JSONL stdout record as it arrives.

    Resolves and execs the binary's absolute path via
    ``asyncio.create_subprocess_exec`` — argv is a list, never a shell string,
    so nothing in ``args`` can be interpreted as shell syntax. Streaming
    line-by-line (rather than collecting all output first) is what lets a
    caller show live progress instead of waiting for the whole scan. A stdout
    line that isn't valid JSON is skipped, not raised — these tools are
    expected to run with ``-silent``, but the odd banner/log line still slips
    through on some versions.
    """
    binary = require(name)
    proc = await asyncio.create_subprocess_exec(
        binary,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert proc.stdout is not None
    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record
    finally:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
