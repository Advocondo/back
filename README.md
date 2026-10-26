# Advocondo — Backend

Este repositório contém o BACKEND do projeto **Advocondo**, um sistema de gestão de contratos voltado para escritórios de advocacia.

## Membros do Grupo

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/eng-Bruno">
        <img style="border-radius: 50%;" src="https://github.com/eng-Bruno.png" width="150px" alt="Bruno Oliveira"/>
        <br />
        <sub><b>Bruno Oliveira</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/ciro-c">
        <img style="border-radius: 50%;" src="https://github.com/ciro-c.png" width="150px" alt="Ciro Costa"/>
        <br />
        <sub><b>Ciro Costa</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/DanNunes777">
        <img style="border-radius: 50%;" src="https://github.com/DanNunes777.png" width="150px" alt="Daniel Nunes Duarte"/>
        <br />
        <sub><b>Daniel Nunes Duarte</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/GabrielaTiago">
        <img style="border-radius: 50%;" src="https://github.com/GabrielaTiago.png" width="150px" alt="Gabriela Tiago de Araújo"/>
        <br />
        <sub><b>Gabriela Tiago de Araújo</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/HauedyWS">
        <img style="border-radius: 50%;" src="https://github.com/HauedyWS.png" width="150px" alt="Hauedy"/>
        <br />
        <sub><b>Hauedy</b></sub>
      </a>
    </td>
  </tr>
  <tr>
    <td align="center">
      <a href="https://github.com/matix0">
        <img style="border-radius: 50%;" src="https://github.com/matix0.png" width="150px" alt="Mateus Vieira"/>
        <br />
        <sub><b>Mateus Vieira</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/PedroHhenriq">
        <img style="border-radius: 50%;" src="https://github.com/PedroHhenriq.png" width="150px" alt="Pedro Henrique"/>
        <br />
        <sub><b>Pedro Henrique</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/Stain19">
        <img style="border-radius: 50%;" src="https://github.com/Stain19.png" width="150px" alt="Pedro Henrique Braga"/>
        <br />
        <sub><b>Pedro Henrique Braga</b></sub>
      </a>
    </td>
  </tr>
</table>


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
├── models.py      # importa todos os modelos (Alembic e testes)
├── common/        # peças compartilhadas (relógio, e-mail, erros, PDF, armazenamento de arquivos)
├── documentos/    # PDF do acordo (ver docs/documentos.md)
├── health.py      # /health e /health/ready
├── logging_config.py  # logs estruturados (JSON)
├── middleware.py  # log por requisição e X-Request-ID
├── security.py    # CORS e HSTS
├── sentry.py      # rastreamento de erros
├── main.py        # criação da aplicação FastAPI
└── __main__.py    # entrypoint de produção (python -m advocondo)
migrations/        # migrations do Alembic (ver docs/migracoes.md)
tests/             # ver docs/testes.md
```

### Verificando o banco

```bash
curl http://localhost:8000/health/ready
```

`/health` só confirma que a API está no ar; `/health/ready` também verifica o banco e as dependências externas. Veja [Observabilidade](docs/observabilidade.md) para os health checks, os logs estruturados e o Sentry.

O login é feito em `POST /auth/login` e as demais rotas recebem o token no cabeçalho `Authorization: Bearer <token>`. Veja [Autenticação](docs/auth.md).

O usuário logado edita o próprio nome, e-mail e senha em `PATCH /users/me`. O Administrador define os condomínios de cada Cliente em `PUT /users/{id}/condominiums`. Veja [Usuários](docs/users.md).

A equipe do escritório cadastra, busca e edita condomínios em `/condominiums`. Veja [Condomínios](docs/condominios.md).

Os devedores de cada condomínio ficam em `/debtors`, com alerta de cadastro duplicado e importação em lote por planilha. Veja [Devedores](docs/devedores.md).

Os acordos com cada devedor ficam em `/agreements`. Veja [Acordos](docs/acordos.md).

O plano de parcelas de cada acordo é gerado no cadastro e editado em `/installments`, onde também ficam as faturas do mês (`GET /installments`) e a baixa de cada parcela, total ou parcial, com o histórico de pagamentos (`/installments/{id}/payment` e `/payments`), e a nota fiscal de cada parcela paga (`/installments/{id}/invoice`). O Administrador vê quem deu baixa, corrigiu, estornou ou editou cada parcela, e as alterações do acordo, em `/agreements/{id}/financial-history`. Veja [Parcelas](docs/parcelas.md).

Quando uma parcela atrasa, o advogado responsável e os Administradores recebem uma notificação no sino, em `/notifications`, criada por um comando diário. Veja [Notificações](docs/notificacoes.md).

O Cliente consulta o status dos acordos dos seus condomínios em `/client-panel`. Veja [Painel do Cliente](docs/painel-cliente.md).

Comissões, faturamento, indicadores e a exportação para Excel ficam em `/operator-panel` e `/admin-panel`. Veja [Painéis financeiros](docs/paineis-financeiros.md).

O conteúdo da landing page fica em `/landing`: o site lê as seções sem login, e o Administrador edita textos e fotos da equipe. Veja [Página institucional](docs/landing.md).

O PDF de cada acordo é gerado e baixado em `/agreements/{id}/pdfs`, com as mesmas permissões do acordo. Veja [Documentos](docs/documentos.md).

### Migrations

O schema do banco é versionado com Alembic. Depois de subir os containers (e sempre que alguém adicionar uma migration), aplique as pendentes:

```bash
docker compose run --rm api uv run alembic upgrade head
```

Sem Docker: `uv run alembic upgrade head`. Veja [Migrations do banco de dados](docs/migracoes.md) para criar uma migration nova e para o deploy.

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
- testes unitários e de integração com relatório de cobertura (pytest-cov), usando um Postgres próprio do job, com o resumo da cobertura no próprio job e o `coverage.xml` como artefato; o job falha se a cobertura de linhas e ramos ficar abaixo de 100%;
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
- Os PDFs gerados ficam no banco, a não ser que as variáveis `S3_` apontem para um bucket S3-compatível (Amazon S3, Cloudflare R2, Backblaze B2). Veja [Documentos](docs/documentos.md#onde-os-arquivos-ficam).
- As variáveis de ambiente e segredos são configurados no painel do Coolify, nunca no repositório. Veja [Variáveis de ambiente e segredos](docs/segredos.md), que também traz a rotina de rotação de credenciais.
- O `docker-compose.yml` é usado só em desenvolvimento.
- As migrations rodam quando o container sobe (`alembic upgrade head` antes da API, no `CMD` do `Dockerfile.prod`); se uma falhar, a versão nova não sobe. Os campos *Pre-deployment* e *Post-deployment* do Coolify ficam vazios. Veja [Migrations do banco de dados](docs/migracoes.md#deploy).
- Depois do primeiro deploy, crie o primeiro Administrador pela rota `POST /setup`, com o `SETUP_TOKEN` configurado. Veja [Autenticação](docs/auth.md#primeiro-administrador).
- Uma *Scheduled Task* diária do Coolify roda `python -m advocondo.auth.cleanup`, que apaga as sessões e os links de redefinição de senha expirados. Veja [Autenticação](docs/auth.md#limpeza-de-sessões-e-links-expirados).
- Outra *Scheduled Task* diária roda `python -m advocondo.notificacoes.overdue`, logo depois da meia-noite de Brasília, que notifica as parcelas que ficaram atrasadas. Veja [Notificações](docs/notificacoes.md#comando-diário).
- `GET /health` é o health check do container; `GET /health/ready` verifica o banco e deve ser usado pelo monitoramento externo.
- HTTPS (certificado e redirecionamento de HTTP) fica no proxy do Coolify, e o CORS libera só o front na Vercel (produção e previews). Veja [HTTPS e CORS](docs/https-cors.md).
- Logs saem em JSON no stdout, e os erros vão para o Sentry quando `SENTRY_DSN` está definida. Veja [Observabilidade](docs/observabilidade.md), que também explica os alertas.

O front-end é publicado separadamente, na Vercel (repositório [`Advocondo/front`](https://github.com/Advocondo/front)).
