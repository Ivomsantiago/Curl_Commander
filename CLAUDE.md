# CurlCommander — project guidance for Claude Code

CurlCommander is a terminal + graphical HTTP request builder, `curl` generator
and API/AppSec testing tool (intercepting proxy, Repeater, Intruder, active/
passive scanners, native MCP server, plugin system). Python 3.11+, `httpx`,
`textual` (TUI), a stdlib web GUI (`curlcommander/webui`), optional extras
(`[browser]`, `[proxy]`, `[mcp]`, `[http2]`, …).

`core/` never imports from `cli/` or `gui/`. Fast checks: `ruff check .`,
`ruff format --check .`, `mypy`, `pytest`.

## Frontend / UI Design

For frontend, GUI, UI or UX work, use the Repaint skill whenever applicable.

Before implementing or redesigning an interface:

- inspect the existing application
- understand the actual workflow and domain
- preserve established interaction patterns
- establish a deliberate visual direction
- avoid generic AI-generated UI patterns

Avoid by default:

- generic SaaS dashboard appearance
- unnecessary card grids
- excessive rounded containers
- excessive pills and badges
- purple/blue gradients
- gradient text
- glassmorphism
- arbitrary glow effects
- excessive shadows
- huge hero headings inside application interfaces
- excessive whitespace
- fake statistics
- decorative charts
- unnecessary dashboard widgets
- emojis used as application icons
- unnecessary decorative icons
- identical three-column layouts
- containers inside containers without semantic reason
- turning every piece of information into a card

Prefer:

- domain-specific interface patterns
- information density appropriate for professional tools
- typography-driven hierarchy
- restrained use of color
- purposeful borders
- fewer containers
- clear interaction hierarchy
- established desktop application conventions
- efficient use of screen space
- functionality over decoration

Curl Commander is a professional security/API/AppSec tool.

Its interface should feel closer to tools such as:

- Burp Suite
- Postman
- Insomnia
- VS Code
- JetBrains IDEs
- mitmproxy
- developer/security tooling

and NOT like a generic marketing SaaS dashboard.

Do not blindly copy those products.
Use them only as references for information density, hierarchy and professional tooling UX.

Before finishing UI work, evaluate:

"Could this exact interface belong to 20 unrelated SaaS products?"

If yes, redesign it until it feels specific to Curl Commander.
