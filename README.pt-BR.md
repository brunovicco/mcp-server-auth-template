# mcp-server-auth-template

[![quality](https://github.com/brunovicco/mcp-server-auth-template/actions/workflows/quality.yml/badge.svg)](https://github.com/brunovicco/mcp-server-auth-template/actions/workflows/quality.yml)
[![compatibility](https://github.com/brunovicco/mcp-server-auth-template/actions/workflows/compatibility.yml/badge.svg)](https://github.com/brunovicco/mcp-server-auth-template/actions/workflows/compatibility.yml)
[![release](https://img.shields.io/github/v/release/brunovicco/mcp-server-auth-template)](https://github.com/brunovicco/mcp-server-auth-template/releases)
![python](https://img.shields.io/badge/python-3.13%20%7C%203.14-blue.svg)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

*[Read in English](README.md)*

Um template reutilizável de servidor MCP que atua como **resource server** OAuth 2.1 - nunca como
authorization server - contra o Microsoft Entra ID ou qualquer authorization server OIDC compatível
com o padrão (Auth0, Keycloak, WorkOS AuthKit, ...). Alvo: especificação MCP **2026-07-28**.

O modelo de autorização do MCP 2026-07-28 mantém um servidor MCP remoto na fronteira de OAuth
resource server: ele publica Protected Resource Metadata e valida access tokens emitidos por um
authorization server externo. Este template implementa essa fronteira para Entra ID e OIDC
genérico, incluindo validação de issuer/audience, obtenção endurecida de JWKS, enforcement de
scopes e os formatos separados de claims delegadas/de aplicação do Entra. Deployments com Entra
usam aplicações cliente pré-registradas; o registro do cliente continua sendo responsabilidade do
authorization server. Veja `docs/adr/0002-oauth21-resource-server.md` para o raciocínio completo e
o repositório companheiro,
[`mcp-client-auth-template`](https://github.com/brunovicco/mcp-client-auth-template), para a
metade cliente desse padrão.

O servidor também anuncia a extensão draft
`io.modelcontextprotocol/oauth-client-credentials`. O perfil determinístico do client companheiro
prova um cliente máquina OIDC genérico pré-registrado com scopes vinculados ao recurso. Tokens
app-only do Entra continuam sendo um contrato separado: o servidor classifica `idtyp=app` e mantém
`roles` distintos de `scp` delegado, mas aquisição real de token Entra não é reivindicada pelo E2E
local.

## Compatibilidade

A release `v0.3.0` suporta Python **3.13 e 3.14**, MCP Python SDK **2.x**
(`>=2.0,<3`) e o perfil de referência MCP **2026-07-28**. O CI exercita continuamente o piso do
SDK (`2.0.0`) e o 2.x compatível mais recente, os dois providers de autenticação, HTTPS de
produção, perfis locais IPv4/IPv6 explicitamente habilitados e o contrato versionado do par
cliente/servidor. O par inclui CIMD/DCR interativo e client credentials OIDC genérico não interativo.

Veja [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md) para a política executável de suporte e seu
escopo. Interoperabilidade ao vivo com IdPs específicos não é reivindicada pela matriz local
determinística.

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
   chamador (client ID, subject, scopes), enquanto `health` demonstra autorização progressiva ao
   exigir o scope adicional `mcp:tools:health`. Um cliente compatível trata o desafio `403` anterior
   ao dispatch reautorizando com a união dos scopes original e elevado.

   `whoami` também aceita um token client-credentials genérico válido. Esse perfil prova client
   ID/subject e scopes da máquina sem inferir app roles do Entra.

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
