# Official MCP Registry

Este repositório está preparado para publicação como:

```text
io.github.brunovicco/mcp-server-auth-template
```

O metadata do Registry não declara um serviço hospedado. O projeto publica um pacote OCI público no
GHCR, mas hoje não opera um endpoint `/mcp` público e estável. Por isso, `server.json` declara um
pacote OCI com Streamable HTTP e não declara `remotes`.

## Vínculo de versão e pacote

Os valores abaixo devem evoluir juntos:

```text
pyproject.toml project.version
server.json version
server.json packages[0].version
tag OCI v<version>
tag Git v<version>
```

A tag `latest` nunca é usada. O workflow seguro de release resolve a tag versionada para o digest
imutável do OCI index multiarch final e registra esse digest como evidência da release.

## Ownership OCI

O Official MCP Registry comprova ownership do pacote OCI por este label da imagem:

```text
io.modelcontextprotocol.server.name=io.github.brunovicco/mcp-server-auth-template
```

O projeto valida o label no Dockerfile, nas imagens construídas em CI e em cada candidato de release
antes da autenticação ou publicação no GHCR.

## Perfil do pacote Streamable HTTP

O pacote do Registry inicia a imagem via Docker, publica a porta apenas em loopback e conserva os
mesmos hardenings usados no CI:

```text
--read-only
--tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m
--cap-drop ALL
--security-opt no-new-privileges:true
--publish 127.0.0.1:8000:8000
```

O transporte do pacote é `http://127.0.0.1:8000/mcp`. Os valores de deployment OAuth/OIDC continuam
sendo configuração explícita. O schema atual de `server.json` não expressa inputs condicionais;
portanto, os campos específicos de Entra e generic OIDC são documentados como condicionalmente
obrigatórios, sem marcá-los incorretamente como obrigatórios para todos os providers.

Esse metadata não representa uma promessa de configuração de identidade one-click. Em produção,
o deployment continua responsável por TLS, registro no IdP, consentimento, secrets, proxy e política
de autorização específica da organização.

## Validação

Invariantes do projeto:

```bash
uv run python scripts/validate_registry_metadata.py
```

Validação oficial de schema e semântica:

```bash
publisher_dir="$(mktemp -d)"
bash scripts/install_mcp_publisher.sh "$publisher_dir"
"$publisher_dir/mcp-publisher" validate server.json
```

O instalador fixa a versão atual do publisher e verifica o SHA-256 do archive da plataforma antes da
execução.

Para uma tag de release:

```bash
uv run python scripts/validate_registry_metadata.py --release-tag v0.6.1
```

A publicação fica deliberadamente fora desta etapa. A primeira publicação no Registry só acontece
depois que a release OCI segura `v0.6.1` estiver pública e validada independentemente.
