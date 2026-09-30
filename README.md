# Advocondo — Backend

Backend do Advocondo, sistema de gestão de contratos para escritórios de advocacia.

## Stack

- Python 3.13
- [FastAPI](https://fastapi.tiangolo.com/)
- PostgreSQL 18
- [uv](https://docs.astral.sh/uv/) para gerenciamento de dependências
- Docker / Docker Compose

## Requisitos

- Docker e Docker Compose

## Como rodar (desenvolvimento)

1. Copie o arquivo de variáveis de ambiente (o `.env` não é versionado; veja [Variáveis de ambiente e segredos](docs/segredos.md)):

   ```bash
   cp .env.example .env
   ```

2. Suba os containers:

   ```bash
   docker compose up
   ```

A API ficará disponível em `http://localhost:8000`, com hot reload habilitado (o código-fonte é montado como volume). O Postgres fica exposto em `localhost:5432`.

### Verificando a API

```bash
curl http://localhost:8000/health
```

## Estrutura do projeto

```
src/advocondo/
├── __init__.py
├── config.py      # configurações lidas das variáveis de ambiente
├── db.py          # SQLAlchemy: Base dos modelos, engine e sessão
├── health.py      # /health e /health/ready
├── logging_config.py  # logs estruturados (JSON)
├── middleware.py  # log por requisição e X-Request-ID
├── sentry.py      # rastreamento de erros
├── main.py        # criação da aplicação FastAPI
└── __main__.py    # entrypoint de produção (python -m advocondo)
tests/             # ver docs/testes.md
```

### Verificando o banco

```bash
curl http://localhost:8000/health/ready
```

`/health` só confirma que a API está no ar; `/health/ready` também verifica o banco e as dependências externas. Veja [Observabilidade](docs/observabilidade.md) para os health checks, os logs estruturados e o Sentry.

## Desenvolvimento sem Docker

Com o [uv](https://docs.astral.sh/uv/) instalado:

```bash
uv run fastapi dev src/advocondo/main.py
```

## Lint

O projeto usa [ruff](https://docs.astral.sh/ruff/):

```bash
uv run ruff check .
```

## Testes

Os testes usam [pytest](https://docs.pytest.org/), com cobertura (pytest-cov) exibida ao final da execução. Os testes de integração usam um banco de teste separado (`advocondo_test`) no Postgres do docker-compose:

```bash
docker compose up -d db
uv run pytest
```

Para rodar só os testes que não usam banco: `uv run pytest -m "not integration"`. Veja [Testes automatizados](docs/testes.md) para as fixtures disponíveis, o isolamento entre testes e os exemplos de referência.

## Checagem de tipos

O projeto usa [mypy](https://mypy.readthedocs.io/) em modo estrito:

```bash
uv run mypy
```

## CI

O workflow `.github/workflows/ci.yml` roda em todo push e em todo PR para `main`:

- busca de segredos commitados (gitleaks);
- lint e formatação (ruff);
- checagem de tipos (mypy);
- testes unitários e de integração com relatório de cobertura (pytest-cov), usando um Postgres próprio do job, com o resumo da cobertura no próprio job e o `coverage.xml` como artefato;
- build do `Dockerfile.prod`.

A branch `main` é protegida: o PR só pode ser mergeado se os jobs **Lint e testes** e **Build da imagem de produção** passarem. O deploy (CD) é feito pelo Coolify quando o código chega na `main`.

## Build de produção

O `Dockerfile.prod` faz um build multi-stage, compilando as dependências com `uv` e gerando uma imagem final enxuta, sem `uv`, rodando como usuário não-root. A API sobe com `python -m advocondo`, para que todos os logs saiam em JSON:

```bash
docker build -f Dockerfile.prod -t advocondo-backend .
```

## Deploy

Em produção, o back-end roda em uma instância da **Oracle Cloud**, gerenciada pelo [Coolify](https://coolify.io). O Coolify faz o build com o `Dockerfile.prod` a partir deste repositório e expõe a API na porta `8000`.

- O PostgreSQL de produção roda no mesmo Coolify, e a API se conecta a ele pela `DATABASE_URL`.
- As variáveis de ambiente e segredos são configurados no painel do Coolify, nunca no repositório. Veja [Variáveis de ambiente e segredos](docs/segredos.md), que também traz a rotina de rotação de credenciais.
- O `docker-compose.yml` é usado só em desenvolvimento.
- `GET /health` é o health check do container; `GET /health/ready` verifica o banco e deve ser usado pelo monitoramento externo.
- Logs saem em JSON no stdout, e os erros vão para o Sentry quando `SENTRY_DSN` está definida. Veja [Observabilidade](docs/observabilidade.md), que também explica os alertas.

O front-end é publicado separadamente, na Vercel (repositório [`Advocondo/front`](https://github.com/Advocondo/front)).
