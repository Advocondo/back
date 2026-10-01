# Testes automatizados

Os testes usam [pytest](https://docs.pytest.org/), com cobertura via `pytest-cov`, e rodam no CI em todo push e PR.

## Como rodar

Os testes de integração precisam do PostgreSQL. O mais simples é usar o do docker-compose:

```bash
docker compose up -d db
uv run pytest
```

Ou tudo dentro do container da API:

```bash
docker compose run --rm api uv run pytest
```

Para rodar só os testes que não usam banco:

```bash
uv run pytest -m "not integration"
```

## Banco de dados de teste

- Os testes usam um banco **separado**, definido por `TEST_DATABASE_URL`. Por padrão é `advocondo_test` no Postgres local; no docker-compose o host já vem como `db`.
- O nome do banco **precisa terminar em `_test`**. Os testes apagam e recriam o schema, então se a URL apontar para outro banco a suíte para com erro antes de tocar em qualquer dado.
- O banco é criado automaticamente na primeira execução. O schema é recriado pelas migrations (`alembic upgrade head`, ver [Migrations](migrations.md)) a cada execução da suíte.
- No CI, o job sobe um Postgres próprio, descartado ao final.

## Isolamento entre testes

Cada teste que usa o banco roda dentro de uma transação que sofre **rollback** no final. Os `commit()` feitos pelo código testado viram savepoints dentro dessa transação. Assim:

- todo teste começa com o banco vazio, sem depender da ordem de execução;
- não é preciso limpar tabelas manualmente.

`tests/integration/test_isolamento.py` garante esse comportamento.

## Fixtures disponíveis

Ficam em `tests/conftest.py`:

| Fixture | O que entrega | Usa banco? |
| --- | --- | --- |
| `client` | `TestClient` da API | Não |
| `db_session` | Sessão SQLAlchemy no banco de teste, com rollback ao final | Sim |
| `db_client` | `TestClient` da API usando a `db_session` no lugar da sessão real | Sim |
| `db_engine` | Engine do banco de teste (escopo da suíte inteira) | Sim |

Testes que usam `db_session` ou `db_client` recebem automaticamente o marcador `integration`.

## Organização

```
tests/
├── conftest.py          # fixtures compartilhadas
├── support/             # utilitários dos testes (banco de teste)
├── unit/                # testes sem banco
└── integration/         # testes com banco (API + Postgres)
```

## Exemplos de referência

- **Teste parametrizado:** `tests/unit/test_test_database_guard.py`. Um mesmo teste roda com vários casos via `@pytest.mark.parametrize`, usando `pytest.param(..., id=...)` para dar nomes legíveis aos casos.
- **Teste de integração:** `tests/integration/test_health_ready.py`. Faz uma requisição à API, que usa o banco de teste de verdade.
- **Parametrizado + integração:** `tests/integration/test_isolamento.py`.

## Fixtures de domínio

Os modelos de domínio (acordo, devedor, condomínio, usuário, parcela) ainda não existem; eles vêm com o modelo físico do banco (#42). Quando forem criados, as fixtures de cada domínio devem seguir este padrão:

- uma fixture por entidade, que recebe `db_session`, cria o objeto com valores padrão válidos e o devolve (ex.: `condominio`, `devedor`, `acordo`);
- fixtures que dependem de outras as recebem como parâmetro (ex.: `acordo` recebe `condominio` e `devedor`);
- quando um teste precisar de variações, use uma fixture "fábrica" que recebe os campos a sobrescrever (ex.: `criar_acordo(valor_total=...)`);
- fixtures usadas por mais de um arquivo ficam em `tests/conftest.py`, ou em `tests/fixtures/<dominio>.py` registrado como plugin no `conftest.py`, se o arquivo crescer.

A tabela `rascunho_teste` de `test_isolamento.py` existe só até lá, e pode ser trocada por um modelo real quando houver.
