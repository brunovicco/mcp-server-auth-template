# mcp-server-auth-template

[![quality](https://github.com/brunovicco/mcp-server-auth-template/actions/workflows/quality.yml/badge.svg)](https://github.com/brunovicco/mcp-server-auth-template/actions/workflows/quality.yml)
![python](https://img.shields.io/badge/python-3.13-blue.svg)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

*[Read in English](README.md)*

Um template reutilizável de servidor MCP que atua como **resource server** OAuth 2.1 - nunca como
authorization server - contra o Microsoft Entra ID ou qualquer authorization server OIDC compatível
com o padrão (Auth0, Keycloak, WorkOS AuthKit, ...). Alvo: especificação MCP **2026-07-28**.

A especificação de autorização do MCP 2026-07-28 modela todo servidor MCP remoto dessa forma: ele
verifica bearer tokens emitidos em outro lugar, nunca os emite. O Entra ID também não consegue
atuar como um authorization server MCP completo para clientes arbitrários (sem Dynamic Client
Registration, sem Client ID Metadata Documents), então uma integração real precisa de um adapter de
qualquer forma. Este template é esse adapter, construído uma vez, corretamente, para que um novo
servidor MCP não precise redescobrir cache de JWKS, validação de issuer/audience, e o formato de
claims dividido (`scp`/`roles`) do Entra do zero. Veja
`docs/adr/0002-oauth21-resource-server.md` para o raciocínio completo, e o repositório companheiro,
[`mcp-client-auth-template`](https://github.com/brunovicco/mcp-client-auth-template), para a
metade cliente desse padrão.

## Início rápido (auth)

1. Copie `.env.example` para `.env` e preencha um dos dois blocos de provider
   (Entra ID ou um authorization server OIDC genérico).
2. Rode o servidor:

   ```bash
   uv run uvicorn mcp_server_auth_template.entrypoints.mcp_server:create_app --factory --reload
   ```

   Para uma execução no estilo de produção, use o launcher do repositório:

   ```bash
   uv run python -m mcp_server_auth_template.entrypoints.serve
   ```

   Veja `docs/OPERATIONS.md` para probes, shutdown, container e orientação de Kubernetes.

3. O Protected Resource Metadata é servido automaticamente em
   `/.well-known/oauth-protected-resource` - aponte um cliente MCP para
   `http://localhost:8000/mcp` e ele vai descobrir o authorization server
   configurado a partir dali:

   ```json
   {
     "resource": "https://mcp.example.invalid/",
     "authorization_servers": ["https://as.example.invalid"],
     "bearer_methods_supported": ["header"]
   }
   ```

   Uma requisição sem bearer token (ou com um token inválido) recebe um `401` com um header
   `WWW-Authenticate` apontando de volta para esse mesmo documento de metadados, exatamente como a
   especificação exige - o servidor nunca tem sua própria tela de login:

   ```text
   HTTP/1.1 401 Unauthorized
   www-authenticate: Bearer error="invalid_token", error_description="Authentication required",
     resource_metadata="https://mcp.example.invalid/.well-known/oauth-protected-resource"
   ```

4. Duas tools de exemplo são registradas: `whoami` retorna a identidade carregada pelo token do
   chamador (client ID, subject, scopes), e `health` é um diagnóstico de aplicação autenticado
   para clientes MCP.

Liveness/readiness operacionais são expostos separadamente como `GET /livez` e `GET /readyz` sem
autenticação; veja `docs/OPERATIONS.md` para o contrato de deployment desses endpoints.

Alterne `MCP_SERVER_AUTH_PROVIDER` entre `entra` e `generic` para trocar de adapter - nenhuma outra
mudança de código é necessária. Veja `src/mcp_server_auth_template/adapters/` para as duas
implementações de `TokenVerifier` e `tests/unit/test_*_token_verifier.py` para como cada uma é
testada offline com um JWT assinado localmente (sem rede, sem IdP real).

## Fluxo de autenticação

`docs/ARCHITECTURE.md` tem um diagrama de sequência do ciclo completo do bearer token - o desafio
401, a descoberta do Protected Resource Metadata, a obtenção do token no authorization server (fora
do escopo deste repositório), e a verificação de assinatura/issuer/audience em cada chamada
seguinte. Veja [Diagrams](docs/ARCHITECTURE.md#diagrams).

## Desenvolvimento

```bash
uv lock --check
uv sync --frozen --all-groups --extra observability
uv run pytest
uv run python scripts/quality_gate.py
```

Liste ou selecione checks do gate com `--list` e `--check NAME`. Veja `AGENTS.md` para os
requisitos de build, lint, format, typecheck, test, security, architecture, MCP e conclusão, e
`docs/DEVELOPMENT.md` para o build do container e o setup local.

O Codex carrega o `.codex/config.toml`, `.codex/hooks.json` e `.agents/skills/` já versionados
apenas dentro do contexto de projeto/confiança apropriado. Revise os hooks de lifecycle com
`/hooks` antes de usar.

## Licença

[MIT](LICENSE)
