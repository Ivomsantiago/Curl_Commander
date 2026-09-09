# Security Policy

## Supported Versions

Apenas a versão principal mais recente do CurlCommander recebe atualizações de segurança.

| Versão | Suportada          |
| ------ | ------------------ |
| 6.1.x  | :white_check_mark: |
| < 6.1  | :x:                |

## Como Reportar uma Vulnerabilidade

Levamos a segurança do CurlCommander muito a sério. Se você descobrir uma vulnerabilidade de segurança neste projeto, por favor, reporte-a de forma privada.

**Não abra uma issue pública.**

Em vez disso, utilize o recurso de **Private Vulnerability Reporting** no GitHub:
1. Acesse a aba [Security](https://github.com/Ivomsantiago/Curl_Commander/security/advisories) deste repositório.
2. Clique em **Report a vulnerability** (ou "Reportar uma vulnerabilidade").
3. Forneça os detalhes sobre a vulnerabilidade, incluindo passos para reproduzi-la.

Nós avaliaremos o relatório e responderemos o mais rápido possível.

## Métricas de Segurança & Qualidade (Security and Quality)

Este repositório utiliza múltiplas camadas de verificações automatizadas de segurança para garantir a qualidade e proteção do código (conforme a aba de Segurança do GitHub):

- **Dependabot Alerts**: Habilitado para monitorar e alertar automaticamente sobre vulnerabilidades em dependências de terceiros.
- **Secret Scanning**: Habilitado para detectar e prevenir o vazamento acidental de segredos, tokens (ex: GitHub PATs, chaves da AWS) e senhas no código.
- **Code Scanning**: Escaneamento estático de código integrado na nossa esteira CI/CD (via Semgrep/Ruff/Bandit) para capturar falhas de segurança durante o build.
- **Private Vulnerability Reporting**: Habilitado para permitir o reporte seguro de falhas.
- **Security Advisories**: Ativo para divulgação responsável de patches de segurança.

### Segurança Integrada na Ferramenta
O CurlCommander também atua como uma ferramenta de AppSec. Ele inclui:
- **Análise Passiva**: Escaneamento em tempo real de respostas HTTP buscando vazamento de dados sensíveis e falta de cabeçalhos de segurança (Security Headers).
- **Análise Ativa**: Disparo automático de payloads heurísticos para detecção de vulnerabilidades comuns (XSS, SQLi) em APIs e aplicações web.
