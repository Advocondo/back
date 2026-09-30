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

1. Copie o arquivo de variáveis de ambiente:

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
└── main.py        # entrypoint da aplicação FastAPI
```

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

Os testes usam [pytest](https://docs.pytest.org/). A cobertura (pytest-cov) é exibida ao final da execução:

```bash
uv run pytest
```

## Checagem de tipos

O projeto usa [mypy](https://mypy.readthedocs.io/) em modo estrito:

```bash
uv run mypy
```

## CI

O workflow `.github/workflows/ci.yml` roda em todo push e em todo PR para `main`:

- lint e formatação (ruff);
- checagem de tipos (mypy);
- testes com relatório de cobertura (pytest-cov), com o resumo no próprio job e o `coverage.xml` como artefato;
- build do `Dockerfile.prod`.

A branch `main` é protegida: o PR só pode ser mergeado se os jobs **Lint e testes** e **Build da imagem de produção** passarem. O deploy (CD) é feito pelo Coolify quando o código chega na `main`.

## Build de produção

O `Dockerfile.prod` faz um build multi-stage, compilando as dependências com `uv` e gerando uma imagem final enxuta, sem `uv`, rodando como usuário não-root:

```bash
docker build -f Dockerfile.prod -t advocondo-backend .
```

## Deploy

Em produção, o back-end roda em uma instância da **Oracle Cloud**, gerenciada pelo [Coolify](https://coolify.io). O Coolify faz o build com o `Dockerfile.prod` a partir deste repositório e expõe a API na porta `8000`.

- O PostgreSQL de produção roda no mesmo Coolify, e a API se conecta a ele pela `DATABASE_URL`.
- As variáveis de ambiente são configuradas no painel do Coolify (veja `.env.example`).
- O `docker-compose.yml` é usado só em desenvolvimento.
- Use `GET /health` para verificar se a API está no ar.

O front-end é publicado separadamente, na Vercel (repositório [`Advocondo/front`](https://github.com/Advocondo/front)).
