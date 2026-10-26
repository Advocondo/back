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

- Os testes usam um banco **separado**, definido por `TEST_DATABASE_URL`. O docker-compose a define (host `db`) e o CI também.
- A configuração da aplicação nos testes vem do `.env.example` (fixture `settings`), não do `.env` de quem roda. Testes que dependem de um valor de configuração leem o valor de `settings`, em vez de repetir o número.
- Antes de importar a aplicação, os testes preenchem com o `.env.example` as variáveis que faltarem no ambiente (`tests/support/environment.py`), sem sobrescrever as que já existem. É o que permite rodar no CI, que só define `TEST_DATABASE_URL`.
- O nome do banco **precisa terminar em `_test`**. Os testes apagam e recriam o schema, então se a URL apontar para outro banco a suíte para com erro antes de tocar em qualquer dado.
- O banco é criado automaticamente na primeira execução. Cada execução cria um schema PostgreSQL temporário, constrói nele as tabelas a partir dos modelos (`Base.metadata`) e o remove ao terminar. Tabelas antigas no schema `public` da base não são alteradas. As migrations são testadas à parte, em `test_app_integration.py` (ver [Migrations](migracoes.md#testes)).
- No CI, o job sobe um Postgres próprio, descartado ao final.

## Isolamento entre testes

Cada teste que usa o banco roda dentro de uma transação que sofre **rollback** no final. Os `commit()` feitos pelo código testado viram savepoints dentro dessa transação. Assim:

- todo teste começa com o banco vazio, sem depender da ordem de execução;
- não é preciso limpar tabelas manualmente.

`src/advocondo/test_app_integration.py` garante esse comportamento.

## Fixtures disponíveis

Ficam em `conftest.py` (raiz do projeto) e, as de domínio, em `tests/fixtures/`:

| Fixture | O que entrega | Usa banco? |
| --- | --- | --- |
| `client` | `TestClient` da API | Não |
| `db_session` | Sessão SQLAlchemy no banco de teste, com rollback ao final | Sim |
| `db_client` | `TestClient` da API usando a `db_session` e o relógio `clock` | Sim |
| `clock` | Relógio congelado (`FrozenClock`) injetado na API; `clock.advance(timedelta(...))` avança o tempo | Não |
| `create_user(...)` | Fábrica de usuários ativos, com a senha `DEFAULT_PASSWORD`; aceita `email`, `role`, `status`, `password` | Sim |
| `create_condominium(...)` | Grava um condomínio direto no banco; os campos informados substituem os padrões (`name="Residencial Mirante"`) | Sim |
| `create_debtor(condominium, ...)` | Grava um devedor do condomínio direto no banco; os campos informados substituem os padrões | Sim |
| `landing_page` | Grava as 10 seções da página institucional (`LANDING_CONTENT`), como faz a migration em produção | Sim |
| `authenticate_as(user)` | Cria uma sessão para o usuário e devolve os cabeçalhos `Authorization` | Sim |
| `outbox` | Captura os e-mails que a API envia (`outbox.messages`), em vez de entregá-los; o `db_client` já usa | Não |
| `db_engine` | Engine do banco de teste (escopo da suíte inteira) | Sim |

Testes que usam `db_session` ou `db_client` recebem automaticamente o marcador `integration`.

## Organização

Os testes ficam dentro do módulo que testam, ao lado do código, sem subpasta. Cada módulo tem no máximo dois arquivos de teste, e o tipo aparece no nome: `test_<módulo>_unit.py` (sem banco) e `test_<módulo>_integration.py` (com banco, pela API).

```
conftest.py                              # fixtures compartilhadas
src/advocondo/
├── auth/
│   └── test_auth_integration.py
├── users/
│   ├── test_users_unit.py
│   └── test_users_integration.py
├── common/
│   └── test_common_unit.py
├── test_app_unit.py                     # arquivos fora de um módulo (health, logging, security, sentry)
└── test_app_integration.py              # readiness, isolamento entre testes, migrations
tests/
├── fixtures/                            # fábricas de entidades usadas por vários módulos
└── support/                             # utilitários dos testes (banco, relógio, settings)
```

Dentro de cada arquivo, os testes ficam agrupados em uma classe por assunto ou história (`class TestLogin`, `class TestFirstAdminSetup`), e cada teste é um método que recebe `self` antes das fixtures. Constantes e funções auxiliares ficam no nível do módulo, acima das classes; fixtures de um só assunto ficam dentro da classe. Para rodar um assunto: `pytest src/advocondo/users -k TestFirstAdminSetup`. Se um arquivo passar de umas 500 linhas, o domínio provavelmente deveria ser dividido em dois módulos.

O marcador `integration` é aplicado automaticamente a quem usa `db_session` ou `db_client`. O `pytest` varre `src` e `tests` (`testpaths`), e a cobertura ignora os arquivos `test_*.py`.

## Exemplos de referência

- **Teste parametrizado:** `src/advocondo/test_app_unit.py`. Um mesmo teste roda com vários casos via `@pytest.mark.parametrize`, usando `pytest.param(..., id=...)` para dar nomes legíveis aos casos.
- **Teste de integração:** `src/advocondo/test_app_integration.py`. Faz uma requisição à API, que usa o banco de teste de verdade.
- **Parametrizado + integração:** `src/advocondo/test_app_integration.py`.
- **Conteúdo de PDF:** `src/advocondo/documentos/test_documentos_integration.py`. O texto do PDF é extraído com `pdf_text` (`tests/support/pdf.py`), e o bucket é simulado por um cliente S3 em memória (`tests/support/storage.py`).

## Fixtures de domínio

Usuários já têm fixtures (`tests/fixtures/users.py` e `tests/fixtures/auth.py`). Para os próximos domínios (acordo, devedor, condomínio, parcela), siga este padrão:

- uma fixture por entidade, que recebe `db_session`, cria o objeto com valores padrão válidos e o devolve (ex.: `condominio`, `devedor`, `acordo`);
- fixtures que dependem de outras as recebem como parâmetro (ex.: `acordo` recebe `condominio` e `devedor`);
- quando um teste precisar de variações, use uma fixture "fábrica" que recebe os campos a sobrescrever (ex.: `criar_acordo(valor_total=...)`);
- fixtures usadas por mais de um arquivo ficam em `conftest.py`, ou em `tests/fixtures/<dominio>.py` registrado como plugin no `conftest.py`, se o arquivo crescer.

A tabela `rascunho_teste` de `test_app_integration.py` usa um `metadata` próprio, fora do `Base` da aplicação: não é modelo do domínio e por isso não tem migration. O próprio teste a cria e a remove.
