# Guia de verificação

Este repositório é o dono da fronteira de **resource server** MCP. O
[`mcp-client-auth-template`](https://github.com/brunovicco/mcp-client-auth-template) é o dono do
harness executável entre os dois repositórios, mantendo uma única fonte de verdade para a
orquestração OAuth.

## Prova a partir do código-fonte

Clone os dois repositórios como diretórios irmãos:

```text
Projects/
├── mcp-client-auth-template/
└── mcp-server-auth-template/
```

A partir do repositório do client:

```bash
./scripts/run_reference_demo.sh \
  --server-root ../mcp-server-auth-template
```

Esse caminho inicia o server a partir do checkout atual e um provider OIDC local determinístico.
Uma execução bem-sucedida comprova:

- startup e readiness reais do server;
- discovery de Protected Resource Metadata;
- Authorization Code + PKCE com CIMD-first no client;
- bearer vinculado ao resource;
- `whoami` autenticado;
- `403 insufficient_scope` antes do dispatch;
- retry elevado e limitado para `health`;
- `401` para audience incorreta;
- ausência de `Mcp-Session-Id`.

Nenhuma credencial de produção ou IdP externo é necessária.

## Prova observável da imagem publicada

A stack de observabilidade é deliberadamente mantida pelo client companheiro:

```bash
./scripts/run_observability_demo.sh --keep
```

Uma execução válida deve terminar com:

```text
P1.7c OBSERVABILITY DEMO PASSED
Collector: positive OTLP receipt
Context:   MCP client/server share one trace_id
Tempo:     trace query succeeded
Grafana:   Tempo datasource provisioned
Privacy:   OAuth/MCP sensitive values absent
```

A prova cobre a imagem publicada do server por digest imutável e verifica:

- recebimento OTLP positivo;
- um único trace distribuído entre client e server;
- `service.name=mcp-server-auth-template` nos spans do server;
- consulta bem-sucedida no Tempo;
- datasource Tempo provisionado no Grafana;
- ausência de tokens OAuth, scopes/resource e demais dados protegidos MCP na telemetria.

Após a inspeção, encerre a stack retida usando o comando de stop do client companheiro.

## Evidência visual

O README principal usa três assets versionados:

```text
docs/assets/server-reference-demo.gif
docs/assets/server-observability-trace.png
docs/assets/server-observability-trace-detail.png
```

Eles devem vir de execuções bem-sucedidas dos caminhos acima. Não use screenshots mockados,
banners de sucesso editados manualmente ou traces sintéticos.

O GIF deve mostrar o comando de referência usando o código-fonte e o resultado determinístico de
sucesso. As telas de trace devem deixar visíveis o serviço/spans `mcp-server-auth-template` e,
quando possível, a relação client/server no mesmo trace.

Nunca capture bearer tokens, JWTs, authorization codes, cookies, client secrets, material de
assinatura, argumentos/resultados MCP completos, dados pessoais ou segredos da máquina local.

## Fronteira

O harness do client é infraestrutura de evidência, não dependência de runtime do server. Um
deployment de produção continua sendo responsável por registro no IdP, TLS, network policy,
segredos, capacidade, backend de telemetria, retenção e controles operacionais.
